"""
SECProvider — Tier 1 primary source. Real SEC EDGAR APIs, no API key, no
mocking: ticker->CIK resolution, filing discovery, and full-document fetch.

APIs used:
  https://www.sec.gov/files/company_tickers.json
      Static ticker -> CIK map, published by the SEC. Cached in-process with
      a long TTL (rebuilding it on every call would be one more request per
      research run for data that changes rarely).
  https://data.sec.gov/submissions/CIK{cik:010d}.json
      A company's filing history. We only read `filings.recent` (the most
      recent ~1000 filings) — older filings live in paginated
      `filings.files` entries. Not fetched in this milestone; see the
      docstring on discover() for why that's a deliberate scope cut, not an
      oversight.

Compliance, not a suggestion:
  SEC requires a descriptive User-Agent on every request
  (https://www.sec.gov/os/webmaster-faq#developers) and rate-limits at
  ~10 req/sec. Both are enforced here, not left to the caller: fetch/discover
  raise immediately if sec_edgar_user_agent isn't configured, and every
  request goes through _throttled_get(), which guarantees a minimum gap
  between requests from this process.
"""
import asyncio
import time
from datetime import date, datetime
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.cache import cache_get, cache_set
from app.documents.providers.base import DocumentProvider, DiscoveredDocument, FetchedDocument

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Our doc_type vocabulary -> the SEC "form" values that satisfy it.
DOC_TYPE_TO_FORMS = {
    "10-K": ["10-K", "10-K/A"],
    "10-Q": ["10-Q", "10-Q/A"],
    "8-K": ["8-K", "8-K/A"],
    "DEF-14A": ["DEF 14A"],
    "FORM-4": ["4"],
    "FORM-13F": ["13F-HR", "13F-HR/A"],
}
FORM_TO_DOC_TYPE = {form: doc_type for doc_type, forms in DOC_TYPE_TO_FORMS.items() for form in forms}

_MIN_REQUEST_INTERVAL = 0.12  # ~8.3 req/sec, safely under SEC's 10 req/sec ceiling


class SECProvider(DocumentProvider):
    source_name = "sec_edgar"
    source_tier = 1
    immutable_once_ingested = True  # accession numbers never change content once filed

    def __init__(self):
        self._last_request_at = 0.0
        self._throttle_lock = asyncio.Lock()

    def _user_agent(self) -> str:
        ua = get_settings().sec_edgar_user_agent.strip()
        if not ua:
            raise RuntimeError(
                "SEC_EDGAR_USER_AGENT is not configured. SEC requires a descriptive "
                "User-Agent on every request (https://www.sec.gov/os/webmaster-faq#developers) "
                "— set it in .env before ingesting SEC filings."
            )
        return ua

    async def _throttled_get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < _MIN_REQUEST_INTERVAL:
                await asyncio.sleep(_MIN_REQUEST_INTERVAL - elapsed)
            response = await client.get(url, headers={"User-Agent": self._user_agent()})
            self._last_request_at = time.monotonic()
            return response

    async def _resolve_cik(self, client: httpx.AsyncClient, ticker: str) -> Optional[str]:
        mapping = cache_get("sec_edgar:ticker_cik_map")
        if mapping is None:
            resp = await self._throttled_get(client, _TICKERS_URL)
            resp.raise_for_status()
            raw = resp.json()
            mapping = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in raw.values()}
            cache_set("sec_edgar:ticker_cik_map", mapping, ttl=24 * 3600)
        return mapping.get(ticker.upper())

    async def discover(
        self, ticker: Optional[str], doc_types: list[str], since: Optional[date] = None
    ) -> list[DiscoveredDocument]:
        """
        List filings for `ticker` matching `doc_types` from the company's
        recent filing history.

        Scope cut: only `filings.recent` (SEC's own ~1000-most-recent-filings
        window) is read. Full historical backfill via the paginated
        `filings.files` index is a real, well-defined next step — not built
        here to keep this milestone's surface area to what's actually
        verified end-to-end. For 10-K/DEF-14A (annual) and 10-Q (quarterly)
        filers this window already covers a decade or more; it's most
        limiting for high-frequency 8-K filers, which is an acceptable gap
        for a first ingestion pass, not a silent data-quality issue.
        """
        if not ticker:
            return []
        wanted_forms = {form for dt in doc_types for form in DOC_TYPE_TO_FORMS.get(dt, [])}
        if not wanted_forms:
            return []

        async with httpx.AsyncClient(timeout=20.0) as client:
            cik = await self._resolve_cik(client, ticker)
            if not cik:
                return []

            resp = await self._throttled_get(client, _SUBMISSIONS_URL.format(cik=cik))
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

        company_name = data.get("name")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])

        cik_int = str(int(cik))  # archive URLs use the CIK without leading zeros
        discovered: list[DiscoveredDocument] = []

        for i, form in enumerate(forms):
            if form not in wanted_forms:
                continue

            filing_date_str = filing_dates[i] if i < len(filing_dates) else None
            filing_date_val = _parse_date(filing_date_str)
            if since and filing_date_val and filing_date_val < since:
                continue

            accession = accession_numbers[i] if i < len(accession_numbers) else None
            primary_doc = primary_documents[i] if i < len(primary_documents) else None
            if not accession or not primary_doc:
                continue

            accession_nodashes = accession.replace("-", "")
            source_url = f"{_ARCHIVES_BASE}/{cik_int}/{accession_nodashes}/{primary_doc}"
            doc_type = FORM_TO_DOC_TYPE.get(form, form)
            report_date_val = _parse_date(report_dates[i]) if i < len(report_dates) else None

            discovered.append(DiscoveredDocument(
                external_id=accession,
                provider_source=self.source_name,
                doc_type=doc_type,
                title=f"{company_name} {doc_type} ({filing_date_str})",
                source_url=source_url,
                ticker=ticker.upper(),
                company_name=company_name,
                cik=cik,
                filing_date=filing_date_val,
                period_end_date=report_date_val,
            ))

        return discovered

    async def fetch(self, discovered: DiscoveredDocument) -> FetchedDocument:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await self._throttled_get(client, discovered.source_url)
            resp.raise_for_status()
            raw_format = "pdf" if discovered.source_url.lower().endswith(".pdf") else "html"
            return FetchedDocument(
                discovered=discovered,
                raw_format=raw_format,
                raw_content=resp.text if raw_format == "html" else resp.content,
            )


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
