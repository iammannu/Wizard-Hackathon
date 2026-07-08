"""
DocumentProvider — the one interface every document source implements.

Why it exists:
  "Each provider should expose the same interface. This allows us to
  replace providers later without changing the research pipeline." The
  ingestion service (app/documents/services/ingestion_service.py) only ever
  talks to this interface — it doesn't know or care whether it's driving
  SECProvider, a future InvestorRelationsProvider, or a
  SearchDiscoveryProvider that's really just wrapping You.com/Tavily to
  *locate* a Tier 2 document. Swapping or adding a provider never touches
  ingestion_service, retrieval, or anything upstream of this package.

Two-phase discover/fetch split, not a single fetch_all():
  discover() is cheap (index/metadata lookups) and answers "what exists
  that we might not have yet." fetch() is expensive (downloads and returns
  full content) and only runs for documents ingestion_service decides are
  actually new or changed (via Document.content_hash / external_id).
  Collapsing these into one call would mean re-downloading full documents
  just to check whether anything changed.

Tiering is a fact about the provider, not the interface: source_tier lets
the ingestion/evidence layers reason about "did this claim come from a
primary source or a search-discovered one" without hardcoding provider
names.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class DiscoveredDocument:
    """What discover() returns — enough to decide whether to fetch, not the content itself."""
    external_id: str
    provider_source: str
    doc_type: str
    title: str
    source_url: str
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    cik: Optional[str] = None
    filing_date: Optional[date] = None
    period_end_date: Optional[date] = None


@dataclass
class FetchedDocument:
    """What fetch() returns — raw content ready for app/documents/parsers/."""
    discovered: DiscoveredDocument
    raw_format: str  # "html" | "pdf" | "text"
    raw_content: str | bytes  # str for html/text, bytes for pdf


class DocumentProvider(ABC):
    #: "sec_edgar" | "investor_relations" | "transcript" | "press_release" | "search_discovery"
    source_name: str
    #: 1 = SEC EDGAR primary sources, 2 = official company sources, 3 = search discovery/verification
    source_tier: int
    #: True if content under a given external_id can never change once
    #: ingested (e.g. a SEC accession number — an amendment gets a *new*
    #: accession number, never a mutation of the old one). Lets
    #: ingestion_service skip re-fetching entirely once a document reaches a
    #: terminal status. Sources where the same URL/external_id can be
    #: corrected in place after publication (a press release, an IR page)
    #: MUST leave this False so content_hash comparison actually runs on
    #: every ingest — otherwise an in-place edit is silently never picked up.
    immutable_once_ingested: bool = False

    @abstractmethod
    async def discover(
        self, ticker: Optional[str], doc_types: list[str], since: Optional[date] = None
    ) -> list[DiscoveredDocument]:
        """List candidate documents without downloading full content."""
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, discovered: DiscoveredDocument) -> FetchedDocument:
        """Download the full content for one document discover() returned."""
        raise NotImplementedError
