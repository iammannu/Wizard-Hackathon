"""
Unit tests for the Evidence Engine (Milestone 2).

No pytest-asyncio dependency: async pieces are driven with asyncio.run()
inside plain `def test_...()` functions, so no new test-runner dependency
is needed beyond the `pytest` already installed.

The two genuinely external dependencies — the embedding API and the LLM
API — are swapped for small, deterministic stand-ins via monkeypatching
(standard test isolation practice, not a "mock implementation" of any
production code path: extraction, scoring, dedup, citation building, and
pipeline orchestration all run for real against a real in-memory SQLite
database with the actual ORM models). Everything else exercises the real
app/documents/evidence/* modules end to end.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.documents.models.document import Document, DocumentVersion
from app.documents.models.chunk import DocumentChunk
from app.documents.models.embedding import DocumentEmbedding
# Referenced-but-otherwise-unused imports — WorkspaceDocument/ClaimCitation
# (registered by importing app.documents.models.document/.citation above and
# below) have FKs to workspaces/thesis_claims, so Base.metadata.create_all
# needs these registered too or FK resolution fails, even though these
# tests never touch workspaces/theses themselves.
from app.models import workspace as _workspace_models  # noqa: F401
from app.models import thesis as _thesis_models  # noqa: F401
from app.documents.models import citation as _citation_models  # noqa: F401
from app.documents.models import entity as _entity_models  # noqa: F401

from app.documents.evidence.models import Evidence, EvidenceScore, Citation
from app.documents.evidence.citations import build_citation
from app.documents.evidence import scorer as scorer_mod
from app.documents.evidence.scorer import score_evidence
from app.documents.evidence.dedup import deduplicate
from app.documents.evidence import conflict as conflict_mod
from app.documents.evidence import claims as claims_mod
from app.documents.evidence.extractor import extract_evidence
from app.documents.evidence import service as evidence_service
from app.documents.retrieval.vector_store import ScoredChunk


# ── In-memory DB helper ──────────────────────────────────────────────────

async def _make_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def _seed_document(db, *, filing_date: date, ticker="AAPL", provider_source="sec_edgar", doc_type="10-K"):
    document = Document(
        external_id=f"acc-{uuid.uuid4().hex[:8]}",
        provider_source=provider_source,
        doc_type=doc_type,
        ticker=ticker,
        title=f"{ticker} {doc_type} ({filing_date.isoformat()})",
        filing_date=filing_date,
        source_url="https://example.com/filing",
        status="chunked",
    )
    db.add(document)
    await db.flush()

    version = DocumentVersion(
        document_id=document.id, version_number=1, raw_format="html",
        extracted_text="full text", token_count=100, content_hash="hash-v1",
    )
    db.add(version)
    await db.flush()

    document.latest_version_id = version.id
    document.latest_version_number = 1
    return document, version


async def _seed_chunk(db, document, version, *, text: str, section="item_7", chunk_index=0):
    chunk = DocumentChunk(
        document_id=document.id, document_version_id=version.id, chunk_index=chunk_index,
        section=section, text=text, token_count=len(text.split()), content_hash=f"hash-{chunk_index}-{uuid.uuid4().hex[:6]}",
    )
    db.add(chunk)
    await db.flush()
    return chunk


async def _seed_embedding(db, chunk, document, vector: list[float], provider="openai", model="text-embedding-3-small"):
    import json

    db.add(DocumentEmbedding(
        chunk_id=chunk.id, document_id=document.id, provider=provider, model=model,
        dimension=len(vector), vector=json.dumps(vector), content_hash=chunk.content_hash,
    ))
    chunk.embedding = json.dumps(vector)
    chunk.embedding_model = model
    chunk.embedding_dim = len(vector)
    await db.flush()


def _make_evidence(text: str, section="item_7", overall=0.5, filing_date=None, provider_source="sec_edgar", doc_type="10-K") -> Evidence:
    return Evidence(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Test Doc",
        ticker="AAPL",
        doc_type=doc_type,
        section=section,
        filing_date=filing_date,
        text=text,
        citation=Citation(
            citation_id=f"cit-{uuid.uuid4().hex[:6]}", document_id=uuid.uuid4(), document_title="Test Doc",
            external_id="acc-1", chunk_id=uuid.uuid4(), section=section, provider=provider_source, version=1,
        ),
        score=EvidenceScore(overall=overall),
    )


# ── Citation Builder ─────────────────────────────────────────────────────

def test_build_citation():
    async def run():
        engine, db = await _make_session()
        document, version = await _seed_document(db, filing_date=date(2025, 10, 31))
        chunk = await _seed_chunk(db, document, version, text="Revenue grew 8% year over year.", chunk_index=3)

        citation = build_citation(chunk, document, version.version_number)

        assert citation.citation_id == f"{document.external_id}#chunk-3"
        assert citation.document_id == document.id
        assert citation.chunk_id == chunk.id
        assert citation.section == "item_7"
        assert citation.provider == "sec_edgar"
        assert citation.version == 1
        assert citation.url == "https://example.com/filing"
        await engine.dispose()

    asyncio.run(run())


# ── Evidence Extraction ──────────────────────────────────────────────────

def test_extract_evidence_hydrates_hierarchy_and_version():
    async def run():
        engine, db = await _make_session()
        document, version = await _seed_document(db, filing_date=date(2025, 10, 31))
        chunk = await _seed_chunk(db, document, version, text="Risk factors include supply chain concentration.", section="item_1a")
        await db.commit()

        scored = [ScoredChunk(chunk_id=chunk.id, document_id=document.id, score=0.9, vector=[1.0, 0.0])]
        evidence_list, vectors = await extract_evidence(db, scored)

        assert len(evidence_list) == 1
        e = evidence_list[0]
        assert e.chunk_id == chunk.id
        assert e.document_id == document.id
        assert e.document_title == document.title
        assert e.ticker == "AAPL"
        assert e.doc_type == "10-K"
        assert e.section == "item_1a"
        assert e.filing_date == date(2025, 10, 31)
        assert e.citation.version == 1
        assert e.citation.citation_id == f"{document.external_id}#chunk-0"
        assert vectors[e.id] == [1.0, 0.0]
        await engine.dispose()

    asyncio.run(run())


def test_extract_evidence_skips_missing_chunks_without_crashing():
    async def run():
        engine, db = await _make_session()
        scored = [ScoredChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), score=0.5, vector=[1.0])]
        evidence_list, vectors = await extract_evidence(db, scored)
        assert evidence_list == []
        assert vectors == {}
        await engine.dispose()

    asyncio.run(run())


# ── Evidence Scoring ─────────────────────────────────────────────────────

def test_score_evidence_semantic_similarity_and_overall_bounds():
    evidence = _make_evidence("Revenue grew 8% year over year to $95 billion.", filing_date=date.today())
    vectors = {evidence.id: [1.0, 0.0]}
    query_vector = [1.0, 0.0]

    [scored] = score_evidence([evidence], vectors, "revenue growth", query_vector)

    assert scored.score.semantic_similarity == pytest.approx(1.0, abs=1e-6)
    assert 0.0 <= scored.score.overall <= 1.0
    assert scored.score.keyword_overlap > 0  # "revenue" appears in both query and text


def test_score_evidence_recency_decays_with_age():
    settings = scorer_mod.settings
    recent = _make_evidence("text", filing_date=date.today())
    old = _make_evidence("text", filing_date=date.today() - timedelta(days=365 * (settings.evidence_recency_decay_years + 5)))
    vectors = {recent.id: [0.0], old.id: [0.0]}

    score_evidence([recent, old], vectors, "query", [0.0])

    assert recent.score.recency > old.score.recency
    assert old.score.recency == 0.0


def test_score_evidence_section_importance_ranks_mda_above_preamble():
    mda = _make_evidence("text", section="item_7")
    preamble = _make_evidence("text", section="_preamble")
    vectors = {mda.id: [0.0], preamble.id: [0.0]}

    score_evidence([mda, preamble], vectors, "query", [0.0])

    assert mda.score.section_importance > preamble.score.section_importance


# ── Deduplication ────────────────────────────────────────────────────────

def test_deduplicate_removes_near_duplicates_and_keeps_highest_score():
    high = _make_evidence("Revenue grew 8%.", overall=0.9)
    near_dup = _make_evidence("Revenue increased 8%.", overall=0.5)
    distinct = _make_evidence("Risk factors include competition.", overall=0.7)
    vectors = {
        high.id: [1.0, 0.0],
        near_dup.id: [0.99, 0.01],   # near-identical direction to `high`
        distinct.id: [0.0, 1.0],
    }

    kept, kept_vectors, removed = deduplicate([high, near_dup, distinct], vectors, threshold=0.95)

    kept_ids = {e.id for e in kept}
    assert high.id in kept_ids
    assert near_dup.id not in kept_ids  # lower-scoring near-duplicate dropped
    assert distinct.id in kept_ids
    assert removed == 1
    assert set(kept_vectors) == kept_ids


def test_deduplicate_identical_vectors_treated_as_duplicates():
    a = _make_evidence("Same text.", overall=0.8)
    b = _make_evidence("Same text.", overall=0.6)
    vectors = {a.id: [1.0, 2.0, 3.0], b.id: [1.0, 2.0, 3.0]}

    kept, _, removed = deduplicate([a, b], vectors, threshold=0.95)

    assert len(kept) == 1
    assert kept[0].id == a.id
    assert removed == 1


# ── Conflict Detection ───────────────────────────────────────────────────

def test_detect_conflicts_only_checks_pairs_above_threshold(monkeypatch):
    async def run():
        called_with = {}

        async def fake_llm_json(system, user):
            called_with["user"] = user
            return {"pairs": [{"index": 0, "relationship": "contradicts"}]}

        monkeypatch.setattr(conflict_mod, "llm_json", fake_llm_json)

        similar_a = _make_evidence("Revenue was $10B.")
        similar_b = _make_evidence("Revenue was $12B.")
        unrelated = _make_evidence("Completely different topic.")
        vectors = {similar_a.id: [1.0, 0.0], similar_b.id: [0.95, 0.05], unrelated.id: [0.0, 1.0]}

        summary = await conflict_mod.detect_conflicts([similar_a, similar_b, unrelated], vectors, threshold=0.8)

        assert summary["pairs_checked"] == 1  # only the similar pair crosses the threshold
        assert summary["contradicts_count"] == 1
        assert similar_b.id in similar_a.conflicts_with
        assert similar_a.id in similar_b.conflicts_with
        assert unrelated.conflicts_with == []
        assert "Revenue was $10B" in called_with["user"]

    asyncio.run(run())


def test_detect_conflicts_no_candidate_pairs_skips_llm_call(monkeypatch):
    async def run():
        calls = []

        async def fake_llm_json(system, user):
            calls.append(1)
            return {}

        monkeypatch.setattr(conflict_mod, "llm_json", fake_llm_json)

        a = _make_evidence("Topic A")
        b = _make_evidence("Topic B")
        vectors = {a.id: [1.0, 0.0], b.id: [0.0, 1.0]}

        summary = await conflict_mod.detect_conflicts([a, b], vectors, threshold=0.8)

        assert summary["pairs_checked"] == 0
        assert calls == []  # llm_json never called when no candidate pairs exist

    asyncio.run(run())


def test_detect_conflicts_llm_failure_defaults_to_neutral(monkeypatch):
    async def run():
        async def failing_llm_json(system, user):
            return {}  # llm_json's own never-raise contract on failure

        monkeypatch.setattr(conflict_mod, "llm_json", failing_llm_json)

        a = _make_evidence("Same topic A")
        b = _make_evidence("Same topic B")
        vectors = {a.id: [1.0, 0.0], b.id: [0.95, 0.05]}

        summary = await conflict_mod.detect_conflicts([a, b], vectors, threshold=0.8)

        assert summary["neutral_count"] == 1
        assert summary["contradicts_count"] == 0
        assert a.conflicts_with == []

    asyncio.run(run())


# ── Claim Builder ────────────────────────────────────────────────────────

def test_build_claims_clusters_and_generates_text(monkeypatch):
    async def run():
        async def fake_llm_json(system, user):
            n_groups = user.count("Group ")
            return {"claims": [{"index": i, "text": f"Synthesized claim {i}"} for i in range(n_groups)]}

        monkeypatch.setattr(claims_mod, "llm_json", fake_llm_json)

        a = _make_evidence("Revenue grew 8%.", overall=0.9)
        b = _make_evidence("Revenue increased 8%.", overall=0.8)  # same cluster as a
        c = _make_evidence("Risk factors include competition.", overall=0.7)  # different cluster
        vectors = {a.id: [1.0, 0.0], b.id: [0.95, 0.05], c.id: [0.0, 1.0]}

        claims = await claims_mod.build_claims([a, b, c], vectors, threshold=0.8, max_claims=5)

        assert len(claims) == 2  # two topic clusters
        cluster_sizes = sorted(len(c.supporting_evidence_ids) for c in claims)
        assert cluster_sizes == [1, 2]
        assert all(c.text.startswith("Synthesized claim") for c in claims)

    asyncio.run(run())


def test_build_claims_confidence_penalized_by_contradiction(monkeypatch):
    async def run():
        async def fake_llm_json(system, user):
            return {"claims": [{"index": 0, "text": "A claim"}]}

        monkeypatch.setattr(claims_mod, "llm_json", fake_llm_json)

        a = _make_evidence("Fact A.", overall=0.9)
        b = _make_evidence("Fact B.", overall=0.9)
        b.conflicts_with.append(a.id)
        a.conflicts_with.append(b.id)
        vectors = {a.id: [1.0, 0.0], b.id: [0.99, 0.01]}

        claims = await claims_mod.build_claims([a, b], vectors, threshold=0.8, max_claims=5)

        assert len(claims) == 1
        assert claims[0].confidence == pytest.approx(0.9 - 0.3, abs=1e-6)
        assert set(claims[0].contradictions) == {a.id, b.id}

    asyncio.run(run())


def test_build_claims_falls_back_when_llm_omits_index(monkeypatch):
    async def run():
        async def empty_llm_json(system, user):
            return {}  # simulates llm_json's failure contract

        monkeypatch.setattr(claims_mod, "llm_json", empty_llm_json)

        a = _make_evidence("First sentence here. Second sentence.", overall=0.6)
        claims = await claims_mod.build_claims([a], {a.id: [1.0]}, threshold=0.8, max_claims=5)

        assert len(claims) == 1
        assert claims[0].text == "First sentence here."

    asyncio.run(run())


# ── EvidencePack generation (full pipeline) ──────────────────────────────

class _FakeEmbeddingProvider:
    """Deterministic stand-in for the real OpenAI/Voyage/local providers —
    the only thing build_evidence_pack needs from it is embed_query()."""

    def __init__(self, query_vector):
        self._query_vector = query_vector

    async def embed_query(self, text):
        return self._query_vector


def test_build_evidence_pack_end_to_end(monkeypatch):
    async def run():
        engine, db = await _make_session()
        document, version = await _seed_document(db, filing_date=date.today())

        chunk_a = await _seed_chunk(db, document, version, text="Revenue grew 8 percent year over year to 95 billion dollars.", chunk_index=0, section="item_7")
        chunk_b = await _seed_chunk(db, document, version, text="Revenue increased 8 percent year over year to 95 billion dollars.", chunk_index=1, section="item_7")
        chunk_c = await _seed_chunk(db, document, version, text="Risk factors include supply chain concentration in Asia.", chunk_index=2, section="item_1a")

        await _seed_embedding(db, chunk_a, document, [1.0, 0.0, 0.0])
        await _seed_embedding(db, chunk_b, document, [0.99, 0.01, 0.0])  # near-duplicate of A
        await _seed_embedding(db, chunk_c, document, [0.0, 1.0, 0.0])
        await db.commit()

        monkeypatch.setattr(
            evidence_service, "get_embedding_provider", lambda: _FakeEmbeddingProvider([1.0, 0.0, 0.0])
        )

        async def fake_llm_json(system, user):
            if "Group " in user:
                n = user.count("Group ")
                return {"claims": [{"index": i, "text": f"Claim {i}"} for i in range(n)]}
            return {"pairs": [{"index": 0, "relationship": "supports"}]}

        monkeypatch.setattr(conflict_mod, "llm_json", fake_llm_json)
        monkeypatch.setattr(claims_mod, "llm_json", fake_llm_json)

        pack = await evidence_service.build_evidence_pack(
            db, "revenue growth year over year", ticker="AAPL", top_k=5,
        )

        assert pack.query == "revenue growth year over year"
        # chunk_a and chunk_b are near-duplicates (cosine ~0.9997) — dedup
        # should keep only one of them, so at most one of the two revenue
        # chunks plus the distinct risk-factors chunk survive.
        revenue_survivors = [e for e in pack.evidence if "Revenue" in e.text or "billion" in e.text]
        assert len(revenue_survivors) == 1
        assert len(pack.evidence) >= 1
        assert all(0.0 <= e.score.overall <= 1.0 for e in pack.evidence)
        assert pack.citations  # at least one citation present
        assert 0.0 <= pack.confidence <= 1.0
        assert "candidates_considered" in pack.retrieval_stats
        assert "duplicates_removed" in pack.retrieval_stats
        assert pack.retrieval_stats["duplicates_removed"] >= 1
        assert "contradicts_count" in pack.conflict_summary
        assert pack.metadata.query == "revenue growth year over year"
        assert pack.metadata.ticker == "AAPL"

        await engine.dispose()

    asyncio.run(run())


def test_build_evidence_pack_empty_candidates_returns_empty_pack(monkeypatch):
    async def run():
        engine, db = await _make_session()
        monkeypatch.setattr(evidence_service, "get_embedding_provider", lambda: _FakeEmbeddingProvider([1.0, 0.0]))

        pack = await evidence_service.build_evidence_pack(db, "nothing ingested yet", ticker="ZZZZ")

        assert pack.evidence == []
        assert pack.claims == []
        assert pack.citations == []
        assert pack.confidence == 0.0
        await engine.dispose()

    asyncio.run(run())
