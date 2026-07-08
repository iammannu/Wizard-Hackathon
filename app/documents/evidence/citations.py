"""
Citation Builder — turns a hydrated (DocumentChunk, Document, version_number)
triple into a Citation. Pure function, no DB access, so both
extractor.py (building Evidence) and anything else needing a standalone
citation can call it without a session.

citation_id derivation matches the placeholder scheme already used by
app/documents/retrieval/service.py's RetrievedChunk (Milestone 1) —
f"{external_id}#chunk-{chunk_index}" — kept identical here rather than
introduced as a second, divergent scheme. A real provenance/citation-graph
upgrade (cross-document linking, dedup across identical citations) is
future work per app/documents/models/citation.py's own module docstring;
this module owns the "build one Citation from one chunk" concern.
"""
from app.documents.evidence.models import Citation


def build_citation(chunk, document, version_number: int) -> Citation:
    return Citation(
        citation_id=f"{document.external_id}#chunk-{chunk.chunk_index}",
        document_id=document.id,
        document_title=document.title,
        external_id=document.external_id,
        chunk_id=chunk.id,
        page=chunk.page_number,
        section=chunk.section,
        provider=document.provider_source,
        version=version_number,
        url=document.source_url or None,
    )
