"""
Document Intelligence — AlphaForage's proprietary financial document layer.

Why it exists (read this before adding a provider or touching the pipeline):
  This is not a RAG bolt-on. It is the canonical source of truth the research
  pipeline, Living Thesis, AI Memory, Continuous Monitoring, Alerts,
  Prediction Tracking, Portfolio Intelligence, and Knowledge Graph evolution
  all depend on. Web search (You.com/Tavily) is Tier 3: it verifies and adds
  freshness on top of what's ingested here. It never originates a claim.

Source tiers (see providers/base.py for the shared interface):
  Tier 1 — SEC EDGAR (10-K, 10-Q, 8-K, DEF 14A, Form 4, Form 13F)
  Tier 2 — Official company sources (IR sites, transcripts, investor decks,
           shareholder letters, press releases, product announcements)
  Tier 3 — Search discovery (You.com/Tavily) — locates Tier 2 URLs and
           supplements/verifies; never a primary source itself

Every document gets a stable identifier that survives re-ingestion and
schema changes (SEC accession number for EDGAR filings, a content-derived
hash for everything else) — see models/document.py. Every thesis claim is
expected to resolve to one or more ClaimCitation rows pointing at the exact
document/chunk that backs it — see models/citation.py.

Module map (populated across milestones, see each subpackage's own docstring
for what's live vs. planned):
  models/      ORM models — Document, DocumentVersion, DocumentChunk,
               DocumentEntity, ClaimCitation, WorkspaceDocument
  providers/   DocumentProvider implementations, one per source tier
  parsers/     Raw content (HTML/PDF/text) -> structured sections
  chunking/    Section-aware, token-budgeted chunking
  embeddings/  Embedding generation + caching (milestone 2)
  retrieval/   Hybrid semantic + lexical + metadata retrieval (milestone 2)
  citations/   Claim <-> document provenance linking (milestone 3)
  indexing/    Company-level document index, workspace-level document cache
  services/    The clean entrypoints other subsystems call — this is the
               only part of app/documents/ that anything outside this
               package should import from
"""