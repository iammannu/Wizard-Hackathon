"""
Retrieval router — the agent-facing evidence search endpoint. Application
code should generally go through app.agents.base.search_evidence() (once
agents are wired to call it); this HTTP endpoint exists for direct/manual
queries and for the frontend to explore retrieval results independent of an
agent run.

Milestone 2 (Evidence Engine 2.0): the response is now an EvidencePack
(evidence, claims, citations, confidence, conflict_summary), not a flat
chunk list — see app/documents/evidence/models.py. `results` /
`total_results` / `context_tokens_used` are kept in the response, derived
from the pack's evidence, so a client written against the Milestone 1 shape
still gets a working (if reduced) view rather than a hard break; the
`evidence_pack` field carries the full new structure for clients that want it.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import get_db
from app.documents.retrieval import service as retrieval_service
from app.documents.chunking.chunker import count_tokens

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


class RetrievalQueryRequest(BaseModel):
    query: str
    ticker: Optional[str] = None
    doc_type: Optional[str] = None
    provider_source: Optional[str] = None
    document_ids: Optional[list[str]] = None
    top_k: int = 8
    max_context_tokens: Optional[int] = None
    use_mmr: bool = True
    mmr_lambda: float = 0.5


@router.post("/query")
async def query(body: RetrievalQueryRequest):
    document_ids = None
    if body.document_ids:
        try:
            document_ids = [uuid.UUID(d) for d in body.document_ids]
        except ValueError:
            raise HTTPException(400, "Invalid document_ids — must be UUIDs")

    async for db in get_db():
        pack = await retrieval_service.search(
            db, body.query,
            ticker=body.ticker, doc_type=body.doc_type, provider_source=body.provider_source,
            document_ids=document_ids, top_k=body.top_k, max_context_tokens=body.max_context_tokens,
            use_mmr=body.use_mmr, mmr_lambda=body.mmr_lambda,
        )
        context_tokens_used = sum(count_tokens(e.text) for e in pack.evidence)
        return {
            "query": body.query,
            "evidence_pack": pack.model_dump(mode="json"),
            # Milestone 1-shaped view for backward compatibility.
            "results": [
                {
                    "chunk_id": str(e.chunk_id),
                    "document_id": str(e.document_id),
                    "document_title": e.document_title,
                    "ticker": e.ticker,
                    "doc_type": e.doc_type,
                    "section": e.section,
                    "text": e.text,
                    "score": e.score.overall,
                    "citation_id": e.citation.citation_id,
                }
                for e in pack.evidence
            ],
            "total_results": len(pack.evidence),
            "context_tokens_used": context_tokens_used,
        }
