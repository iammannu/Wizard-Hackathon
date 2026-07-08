"""
SEC filing monitor — reuses app.documents.providers.sec_edgar.SECProvider's
discover() (Tier 1 primary source, already rate-limited/compliant) to detect
newly-filed 10-K/10-Q/8-K/DEF-14A filings.

Self-contained state, no DB read: unlike the Document Intelligence
ingestion pipeline, this monitor tracks "accession numbers already alerted
on" entirely in MonitoringJob.last_state rather than querying the
`documents` table. That keeps Monitor.check() to the same
(ticker, last_state) -> (events, new_state) shape every other monitor uses
— app/monitoring/scheduler.py is the one place that, on a new_filing event,
also triggers real ingestion (it already holds the DB session at that
point in its loop).
"""
from datetime import date

from app.documents.providers.sec_edgar import SECProvider
from app.monitoring.providers.base import Monitor, MonitorEvent

WATCHED_DOC_TYPES = ["10-K", "10-Q", "8-K", "DEF-14A"]


class SECFilingMonitor(Monitor):
    monitor_type = "sec_filing"

    def __init__(self):
        self._provider = SECProvider()

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        try:
            discovered = await self._provider.discover(ticker, WATCHED_DOC_TYPES)
        except RuntimeError:
            # SEC_EDGAR_USER_AGENT not configured — not this monitor's job to
            # fail the whole scheduler tick over a missing config value.
            return [], last_state
        except Exception:
            return [], last_state

        if not discovered:
            return [], last_state

        discovered_sorted = sorted(discovered, key=lambda d: d.filing_date or date.min, reverse=True)
        seen = set(last_state.get("seen_accessions", []))
        first_poll = not last_state.get("seen_accessions")

        events: list[MonitorEvent] = []
        new_accessions: list[str] = []

        for doc in discovered_sorted:
            new_accessions.append(doc.external_id)
            if doc.external_id in seen or first_poll:
                continue
            events.append(MonitorEvent(
                event_type="new_filing",
                title=f"{ticker} filed a new {doc.doc_type}",
                description=doc.title,
                severity="warning" if doc.doc_type == "8-K" else "info",
                dedup_key=f"filing:{ticker}:{doc.external_id}",
                data={
                    "doc_type": doc.doc_type,
                    "accession": doc.external_id,
                    "filing_date": doc.filing_date.isoformat() if doc.filing_date else None,
                    "source_url": doc.source_url,
                },
            ))

        updated_seen = list(dict.fromkeys(new_accessions + list(seen)))[:500]
        return events, {**last_state, "seen_accessions": updated_seen}
