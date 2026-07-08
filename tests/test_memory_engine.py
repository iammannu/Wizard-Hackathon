"""
Unit tests for AI Memory (Milestone 3).

Same isolation approach as tests/test_evidence_engine.py: real in-memory
SQLite + real ORM models, with the two external dependencies (embedding API,
LLM API) swapped for small deterministic stand-ins via monkeypatching.
Everything else — extraction parsing, consolidation dedup/contradiction
logic, company rollup, claim promotion, and semantic retrieval ranking —
runs for real against app/memory/*.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import workspace as _workspace_models
from app.models.workspace import Workspace
from app.models import thesis as _thesis_models
from app.models.thesis import ThesisVersion, ThesisClaim
from app.documents.models import citation as _citation_models  # noqa: F401 (FK target registration)
from app.documents.models import entity as _entity_models  # noqa: F401
from app.documents.models import document as _document_models  # noqa: F401
from app.documents.models import chunk as _chunk_models  # noqa: F401
from app.documents.models import embedding as _embedding_models  # noqa: F401

from app.models.memory import WorkspaceMemory, CompanyMemory, ConversationMemory, ThesisMemory
from app.memory.models import MemoryCandidate, MemorySourceCitation
from app.memory import extractor as extractor_mod
from app.memory import consolidator as consolidator_mod
from app.memory import retriever as retriever_mod
from app.memory import service as service_mod
from app.agents.state import AgentState


# ── In-memory DB helper ──────────────────────────────────────────────────

async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def _seed_workspace(db) -> Workspace:
    ws = Workspace(title="Test Workspace")
    db.add(ws)
    await db.flush()
    return ws


class _FakeEmbeddingProvider:
    """Deterministic stand-in — maps known substrings to fixed vectors so
    cosine similarity in tests is fully controlled, not accidental."""

    provider_name = "fake"
    model_name = "fake-embed"

    def __init__(self, vector_by_keyword: dict[str, list[float]], default=(0.0, 0.0, 1.0)):
        self._vector_by_keyword = vector_by_keyword
        self._default = list(default)

    def _vector_for(self, text: str) -> list[float]:
        for keyword, vector in self._vector_by_keyword.items():
            if keyword in text:
                return vector
        return self._default

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector_for(text)


# ── Extractor ─────────────────────────────────────────────────────────────

def test_extract_memory_candidates_filters_invalid_and_low_confidence(monkeypatch):
    async def run():
        async def fake_llm_json(system, user):
            return {"items": [
                {"memory_type": "fact", "content": "AAPL gross margin was 46%.", "confidence": 0.8},
                {"memory_type": "belief", "content": "Weak belief.", "confidence": 0.1},  # below min_confidence
                {"memory_type": "not_a_type", "content": "Invalid type.", "confidence": 0.9},
                {"memory_type": "investment_decision", "content": "Initiate a bullish position.", "confidence": 0.7, "decision_signal": "bullish"},
            ]}

        monkeypatch.setattr(extractor_mod, "llm_json", fake_llm_json)

        state = AgentState(query="How is AAPL doing?", tickers=["AAPL"], recommendation="Buy AAPL")
        candidates = await extractor_mod.extract_memory_candidates(state)

        assert len(candidates) == 2
        types = {c.memory_type for c in candidates}
        assert types == {"fact", "investment_decision"}
        decision = next(c for c in candidates if c.memory_type == "investment_decision")
        assert decision.decision_signal == "bullish"
        assert all(c.tickers == ["AAPL"] for c in candidates)

    asyncio.run(run())


def test_extract_memory_candidates_returns_empty_on_llm_failure(monkeypatch):
    async def run():
        async def failing_llm_json(system, user):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(extractor_mod, "llm_json", failing_llm_json)

        state = AgentState(query="q", tickers=["AAPL"], recommendation="Buy")
        candidates = await extractor_mod.extract_memory_candidates(state)
        assert candidates == []

    asyncio.run(run())


def test_extract_memory_candidates_skips_when_no_recommendation():
    async def run():
        state = AgentState(query="q")  # no recommendation/explanation
        candidates = await extractor_mod.extract_memory_candidates(state)
        assert candidates == []

    asyncio.run(run())


# ── Consolidator: workspace memory dedup/reinforce/contradict ────────────

def test_consolidate_new_candidate_creates_row(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)
        await db.commit()

        monkeypatch.setattr(
            consolidator_mod, "get_embedding_provider",
            lambda: _FakeEmbeddingProvider({"margin": [1.0, 0.0, 0.0]}),
        )

        candidate = MemoryCandidate(memory_type="fact", content="AAPL gross margin was 46%.", confidence=0.8, tickers=["AAPL"])
        affected = await consolidator_mod.consolidate_workspace_memory(db, ws.id, [candidate])

        assert len(affected) == 1
        assert affected[0].content == "AAPL gross margin was 46%."
        assert affected[0].reinforcement_count == 1
        await engine.dispose()

    asyncio.run(run())


def test_consolidate_near_duplicate_reinforces_existing_row(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)

        existing = WorkspaceMemory(
            workspace_id=ws.id, memory_type="fact", content="AAPL gross margin was 46%.",
            tickers="[\"AAPL\"]", confidence=0.6, status="active",
            source_citations="[]", embedding=json.dumps([1.0, 0.0, 0.0]), embedding_model="fake-embed",
            reinforcement_count=1, contradiction_count=0,
        )
        db.add(existing)
        await db.commit()

        monkeypatch.setattr(
            consolidator_mod, "get_embedding_provider",
            lambda: _FakeEmbeddingProvider({"margin": [1.0, 0.0, 0.0]}),  # identical vector -> similarity 1.0
        )

        candidate = MemoryCandidate(memory_type="fact", content="AAPL's gross margin came in at 46%.", confidence=0.9, tickers=["AAPL"])
        affected = await consolidator_mod.consolidate_workspace_memory(db, ws.id, [candidate])

        assert len(affected) == 1
        assert affected[0].id == existing.id
        assert affected[0].reinforcement_count == 2
        # confidence is the weighted average of 0.6 (x1) and 0.9 (x1)
        assert affected[0].confidence == pytest.approx(0.75, abs=1e-3)

        # No second row was created
        from sqlalchemy import select
        result = await db.execute(select(WorkspaceMemory).where(WorkspaceMemory.workspace_id == ws.id))
        assert len(result.scalars().all()) == 1
        await engine.dispose()

    asyncio.run(run())


def test_consolidate_ambiguous_pair_classified_as_contradiction(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)

        existing = WorkspaceMemory(
            workspace_id=ws.id, memory_type="belief", content="AAPL will beat consensus estimates next quarter.",
            tickers="[\"AAPL\"]", confidence=0.7, status="active",
            source_citations="[]", embedding=json.dumps([1.0, 0.0, 0.0]), embedding_model="fake-embed",
            reinforcement_count=1, contradiction_count=0,
        )
        db.add(existing)
        await db.commit()

        # Similarity 0.8 lands in the ambiguous band [contradiction_threshold, dedup_threshold)
        monkeypatch.setattr(
            consolidator_mod, "get_embedding_provider",
            lambda: _FakeEmbeddingProvider({"miss": [0.8, 0.6, 0.0]}),
        )

        async def fake_llm_json(system, user):
            return {"pairs": [{"index": 0, "relationship": "contradicts"}]}

        monkeypatch.setattr(consolidator_mod, "llm_json", fake_llm_json)

        candidate = MemoryCandidate(memory_type="belief", content="AAPL will miss consensus estimates next quarter.", confidence=0.6, tickers=["AAPL"])
        affected = await consolidator_mod.consolidate_workspace_memory(db, ws.id, [candidate])

        # Both the (penalized) existing row and the new contradicting row are returned
        assert len(affected) == 2
        assert existing.contradiction_count == 1
        assert existing.confidence == pytest.approx(0.55, abs=1e-3)  # 0.7 - 0.15
        new_row = next(r for r in affected if r.id != existing.id)
        assert new_row.content == "AAPL will miss consensus estimates next quarter."
        assert new_row.contradiction_count == 1
        await engine.dispose()

    asyncio.run(run())


# ── Consolidator: company memory rollup ──────────────────────────────────

def test_promote_to_company_memory_skips_below_confidence_bar(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)
        low_confidence_row = WorkspaceMemory(
            workspace_id=ws.id, memory_type="fact", content="Minor detail.",
            tickers="[\"AAPL\"]", confidence=0.2, status="active", source_citations="[]",
            embedding=json.dumps([1.0, 0.0]), embedding_model="fake-embed",
        )
        db.add(low_confidence_row)
        await db.commit()

        await consolidator_mod.promote_to_company_memory(db, "AAPL", ws.id, [low_confidence_row])

        from sqlalchemy import select
        result = await db.execute(select(CompanyMemory).where(CompanyMemory.ticker == "AAPL"))
        assert result.scalars().all() == []
        await engine.dispose()

    asyncio.run(run())


def test_promote_to_company_memory_creates_and_reinforces(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws1 = await _seed_workspace(db)
        ws2 = await _seed_workspace(db)
        row1 = WorkspaceMemory(
            workspace_id=ws1.id, memory_type="fact", content="AAPL relies on Foxconn for manufacturing.",
            tickers="[\"AAPL\"]", confidence=0.8, status="active", source_citations="[]",
            embedding=json.dumps([1.0, 0.0]), embedding_model="fake-embed",
        )
        db.add(row1)
        await db.commit()

        monkeypatch.setattr(consolidator_mod, "get_embedding_provider", lambda: _FakeEmbeddingProvider({}, default=[1.0, 0.0]))

        await consolidator_mod.promote_to_company_memory(db, "AAPL", ws1.id, [row1])

        from sqlalchemy import select
        result = await db.execute(select(CompanyMemory).where(CompanyMemory.ticker == "AAPL"))
        company_rows = result.scalars().all()
        assert len(company_rows) == 1
        assert company_rows[0].reinforcement_count == 1
        assert company_rows[0].source_workspaces_list() == [str(ws1.id)]

        # A second workspace's near-identical fact reinforces instead of duplicating
        row2 = WorkspaceMemory(
            workspace_id=ws2.id, memory_type="fact", content="AAPL depends on Foxconn to manufacture its devices.",
            tickers="[\"AAPL\"]", confidence=0.7, status="active", source_citations="[]",
            embedding=json.dumps([1.0, 0.0]), embedding_model="fake-embed",
        )
        db.add(row2)
        await db.commit()

        await consolidator_mod.promote_to_company_memory(db, "AAPL", ws2.id, [row2])

        result = await db.execute(select(CompanyMemory).where(CompanyMemory.ticker == "AAPL"))
        company_rows = result.scalars().all()
        assert len(company_rows) == 1
        assert company_rows[0].reinforcement_count == 2
        assert str(ws2.id) in company_rows[0].source_workspaces_list()
        await engine.dispose()

    asyncio.run(run())


# ── Consolidator: thesis claim promotion ─────────────────────────────────

def test_promote_thesis_claims_creates_thesis_memory_and_sets_fk():
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)

        version = ThesisVersion(workspace_id=ws.id, version_number=1, signal="bullish", conviction_score=0.7, confidence=0.7)
        db.add(version)
        await db.flush()

        claim = ThesisClaim(
            workspace_id=ws.id, thesis_version_id=version.id, claim_type="bull_point",
            claim_text="AAPL services revenue is accelerating.", claim_confidence=0.8,
            first_version=1, last_confirmed_version=3, appearance_count=3, status="confirmed",
        )
        db.add(claim)
        await db.commit()

        created = await consolidator_mod.promote_thesis_claims(db, ws.id, version)

        assert len(created) == 1
        assert created[0].memory_type == "confirmed_belief"
        assert created[0].content == claim.claim_text
        await db.refresh(claim)
        assert claim.memory_id == created[0].id

        # Idempotent: running again finds no more memory_id-is-null confirmed/refuted claims
        created_again = await consolidator_mod.promote_thesis_claims(db, ws.id, version)
        assert created_again == []
        await engine.dispose()

    asyncio.run(run())


# ── Retriever ─────────────────────────────────────────────────────────────

def test_recall_requires_workspace_or_ticker():
    async def run():
        engine, db = await _make_session()
        pack = await retriever_mod.recall(db, "some query")
        assert pack.items == []
        await engine.dispose()

    asyncio.run(run())


def test_recall_ranks_by_similarity_and_confidence(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)

        strong_match = WorkspaceMemory(
            workspace_id=ws.id, memory_type="fact", content="AAPL margin fact.",
            tickers="[]", confidence=0.9, status="active", source_citations="[]",
            embedding=json.dumps([1.0, 0.0]), embedding_model="fake-embed",
        )
        weak_match = WorkspaceMemory(
            workspace_id=ws.id, memory_type="fact", content="Unrelated fact.",
            tickers="[]", confidence=0.9, status="active", source_citations="[]",
            embedding=json.dumps([0.0, 1.0]), embedding_model="fake-embed",
        )
        db.add_all([strong_match, weak_match])
        await db.commit()

        monkeypatch.setattr(retriever_mod, "get_embedding_provider", lambda: _FakeEmbeddingProvider({"margin": [1.0, 0.0]}))

        pack = await retriever_mod.recall(db, "margin query", workspace_id=str(ws.id), top_k=5)

        assert len(pack.items) == 2
        assert pack.items[0].id == strong_match.id
        assert pack.items[0].similarity == pytest.approx(1.0, abs=1e-6)
        assert pack.items[1].id == weak_match.id
        await engine.dispose()

    asyncio.run(run())


# ── Service: full consolidate_research orchestration ─────────────────────

def test_consolidate_research_creates_conversation_and_workspace_memory(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)
        await db.commit()

        async def fake_llm_json(system, user):
            return {"items": [
                {"memory_type": "fact", "content": "AAPL Q3 gross margin was 46.2%.", "confidence": 0.85},
            ]}

        monkeypatch.setattr(extractor_mod, "llm_json", fake_llm_json)
        monkeypatch.setattr(
            consolidator_mod, "get_embedding_provider",
            lambda: _FakeEmbeddingProvider({"margin": [1.0, 0.0]}),
        )

        state = AgentState(query="How is AAPL margin trending?", tickers=["AAPL"], recommendation="Hold AAPL", explanation="Margins are stable.")
        research_id = uuid.uuid4()

        summary = await service_mod.consolidate_research(db, ws.id, research_id, state, thesis_version=None)
        await db.commit()

        assert summary["candidates_extracted"] == 1
        assert summary["workspace_memory_affected"] == 1

        from sqlalchemy import select
        conv_result = await db.execute(select(ConversationMemory).where(ConversationMemory.workspace_id == ws.id))
        conversations = conv_result.scalars().all()
        assert len(conversations) == 1
        assert conversations[0].item_count == 1

        wm_result = await db.execute(select(WorkspaceMemory).where(WorkspaceMemory.workspace_id == ws.id))
        wm_rows = wm_result.scalars().all()
        assert len(wm_rows) == 1
        assert "46.2%" in wm_rows[0].content

        await engine.dispose()

    asyncio.run(run())


def test_consolidate_research_promotes_investment_decision_when_thesis_version_present(monkeypatch):
    async def run():
        engine, db = await _make_session()
        ws = await _seed_workspace(db)

        version = ThesisVersion(
            workspace_id=ws.id, version_number=1, signal="bullish", conviction_score=0.75, confidence=0.8,
            recommendation="Buy AAPL on pullback.", explanation="Strong services growth offsets hardware softness.",
        )
        db.add(version)
        await db.flush()
        await db.commit()

        async def fake_llm_json(system, user):
            return {"items": []}  # no atomic candidates this session, but decision recording is independent

        monkeypatch.setattr(extractor_mod, "llm_json", fake_llm_json)

        state = AgentState(query="Should we buy AAPL?", tickers=["AAPL"], recommendation="Buy AAPL on pullback.", explanation="Strong services growth.")
        summary = await service_mod.consolidate_research(db, ws.id, uuid.uuid4(), state, thesis_version=version)
        await db.commit()

        assert summary["thesis_memories_created"] == 1  # just the investment_decision row (no confirmed/refuted claims yet)

        from sqlalchemy import select
        result = await db.execute(select(ThesisMemory).where(ThesisMemory.workspace_id == ws.id))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].memory_type == "investment_decision"
        assert rows[0].decision_signal == "bullish"
        await engine.dispose()

    asyncio.run(run())
