"""
PgVectorStore — Postgres + pgvector extension as the similarity backend.

Correctness-only implementation: this app runs on sqlite+aiosqlite today
(see app/core/config.py's database_url default), and pgvector fundamentally
cannot run against SQLite — there is no engine to integration-test this
adapter against in this environment. It's written for the day database_url
switches to postgresql+asyncpg://... per CLAUDE.md's scaling path.

Schema caveat, documented rather than glossed over: document_embeddings.vector
is a portable JSON TEXT column (so the same table works on SQLite), not a
native pgvector `vector` column — pgvector's index-accelerated `<=>` operator
needs the latter. This adapter queries by casting the JSON text to a pgvector
value inline (`::vector`), which works correctly but skips pgvector's ANN
index (ivfflat/hnsw), i.e. it's a correct brute-force cosine query today, not
yet an indexed one. Migrating document_embeddings.vector to a real `vector`
column type (and adding an ivfflat/hnsw index) is the natural follow-up once
this store is actually selected against a Postgres target — flagged here
rather than silently assumed done.

Requires `pip install asyncpg` (already a viable driver choice for
postgresql+asyncpg:// — no separate SDK needed beyond what SQLAlchemy uses).
"""
import uuid
from typing import Optional

from sqlalchemy import text

from app.core.config import get_settings
from app.documents.embeddings.provider import get_active_provider_model
from app.documents.retrieval.vector_store import VectorStore, ScoredChunk

settings = get_settings()


class PgVectorStore(VectorStore):
    def __init__(self):
        if not settings.database_url.startswith("postgresql"):
            raise RuntimeError(
                "vector_store_provider=pgvector requires a postgresql database_url "
                "(current: "
                f"{settings.database_url.split('://')[0]}://...). Set DATABASE_URL to "
                "postgresql+asyncpg://... and ensure the pgvector extension "
                "(`CREATE EXTENSION IF NOT EXISTS vector;`) is installed before selecting this store."
            )

    async def similarity_search(
        self,
        db,
        query_vector: list[float],
        top_k: int = 20,
        ticker: Optional[str] = None,
        doc_type: Optional[str] = None,
        provider_source: Optional[str] = None,
        document_ids: Optional[list[uuid.UUID]] = None,
    ) -> list[ScoredChunk]:
        provider, model = get_active_provider_model()

        clauses = ["de.provider = :provider", "de.model = :model"]
        params: dict = {"provider": provider, "model": model, "query_vector": str(query_vector), "top_k": top_k}
        if ticker:
            clauses.append("d.ticker = :ticker")
            params["ticker"] = ticker.upper()
        if doc_type:
            clauses.append("d.doc_type = :doc_type")
            params["doc_type"] = doc_type
        if provider_source:
            clauses.append("d.provider_source = :provider_source")
            params["provider_source"] = provider_source
        if document_ids:
            clauses.append("de.document_id = ANY(:document_ids)")
            params["document_ids"] = [str(d) for d in document_ids]

        sql = text(
            f"""
            SELECT de.chunk_id, de.document_id, de.vector,
                   1 - (de.vector::vector <=> CAST(:query_vector AS vector)) AS score
            FROM document_embeddings de
            JOIN documents d ON d.id = de.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY de.vector::vector <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        )
        result = await db.execute(sql, params)
        rows = result.fetchall()

        import json

        return [
            ScoredChunk(
                chunk_id=uuid.UUID(str(row.chunk_id)),
                document_id=uuid.UUID(str(row.document_id)),
                score=float(row.score),
                vector=json.loads(row.vector),
            )
            for row in rows
        ]
