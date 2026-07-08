"""
Semantic memory retrieval — embeds a query and ranks stored WorkspaceMemory
(scoped to one workspace) and/or CompanyMemory (scoped to one ticker,
cross-workspace) rows by a blend of cosine similarity and recency-decayed
confidence.

Same embedding space as the Evidence Engine and consolidator.py (the active
Settings.embedding_provider) — one provider configured once, reused across
document retrieval, evidence scoring, and memory.

Ranking blends similarity and confidence (0.7 / 0.3) rather than similarity
alone: a highly-confident, well-reinforced memory item that's a decent
semantic match should be able to outrank a barely-relevant item that happens
to score marginally higher on raw cosine similarity — the same reasoning
Evidence Engine's scorer.py applies across its 8 factors, just simplified to
two since memory items don't have citation/section/authority dimensions.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.documents.embeddings.provider import get_embedding_provider
from app.documents.retrieval.similarity import cosine_similarity
from app.models.memory import WorkspaceMemory, CompanyMemory
from app.memory.models import MemoryItem, MemoryPack

settings = get_settings()

_SIMILARITY_WEIGHT = 0.7
_CONFIDENCE_WEIGHT = 0.3


def _decayed_confidence(confidence: float, last_touched: datetime) -> float:
    now = datetime.now(timezone.utc)
    last_touched_aware = last_touched if last_touched.tzinfo else last_touched.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - last_touched_aware).total_seconds() / 86400)
    decayed = confidence - age_days * settings.memory_confidence_decay_per_day
    return max(0.0, min(1.0, decayed))


async def recall(
    db,
    query: str,
    workspace_id: Optional[str] = None,
    ticker: Optional[str] = None,
    top_k: Optional[int] = None,
    memory_types: Optional[list[str]] = None,
) -> MemoryPack:
    """Ranked memory recall across workspace-scoped and/or company-scoped
    memory. At least one of workspace_id/ticker must be given — recall has
    no meaningful "everything" scope, same reasoning as
    app.documents.retrieval.service.search() always requiring a query."""
    top_k = top_k or settings.memory_recall_top_k

    if not workspace_id and not ticker:
        return MemoryPack(query=query, items=[], workspace_id=workspace_id, ticker=ticker)

    provider = get_embedding_provider()
    query_vector = await provider.embed_query(query)

    scored: list[tuple[float, float, object, str, str]] = []  # (rank_score, similarity, row, scope, scope_key)

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(str(workspace_id))
        except ValueError:
            ws_uuid = None
        if ws_uuid is not None:
            query_stmt = select(WorkspaceMemory).where(
                WorkspaceMemory.workspace_id == ws_uuid,
                WorkspaceMemory.status.in_(["active", "resolved"]),
            )
            if memory_types:
                query_stmt = query_stmt.where(WorkspaceMemory.memory_type.in_(memory_types))
            result = await db.execute(query_stmt)
            for row in result.scalars().all():
                vec = row.embedding_vector()
                if not vec:
                    continue
                similarity = cosine_similarity(query_vector, vec)
                confidence = _decayed_confidence(row.confidence, row.updated_at)
                rank_score = similarity * _SIMILARITY_WEIGHT + confidence * _CONFIDENCE_WEIGHT
                scored.append((rank_score, similarity, row, "workspace", str(workspace_id)))

    if ticker:
        query_stmt = select(CompanyMemory).where(
            CompanyMemory.ticker == ticker.upper(), CompanyMemory.status == "active"
        )
        if memory_types:
            query_stmt = query_stmt.where(CompanyMemory.memory_type.in_(memory_types))
        result = await db.execute(query_stmt)
        for row in result.scalars().all():
            vec = row.embedding_vector()
            if not vec:
                continue
            similarity = cosine_similarity(query_vector, vec)
            confidence = _decayed_confidence(row.confidence, row.last_confirmed_at)
            rank_score = similarity * _SIMILARITY_WEIGHT + confidence * _CONFIDENCE_WEIGHT
            scored.append((rank_score, similarity, row, "company", row.ticker))

    scored.sort(key=lambda entry: entry[0], reverse=True)

    items: list[MemoryItem] = []
    for rank_score, similarity, row, scope, scope_key in scored[:top_k]:
        is_workspace = scope == "workspace"
        items.append(MemoryItem(
            id=row.id,
            scope=scope,
            scope_key=scope_key,
            memory_type=row.memory_type,
            content=row.content,
            confidence=row.confidence,
            status=row.status,
            similarity=round(similarity, 4),
            reinforcement_count=row.reinforcement_count,
            contradiction_count=row.contradiction_count,
            source_citations=row.citations_list(),
            created_at=row.created_at if is_workspace else row.first_seen_at,
            updated_at=row.updated_at if is_workspace else row.last_confirmed_at,
        ))

    return MemoryPack(query=query, items=items, workspace_id=workspace_id, ticker=ticker)
