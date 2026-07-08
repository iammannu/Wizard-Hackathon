"""
Monitor provider interface — the one shape every one of the six monitor
types (app/monitoring/providers/*.py) implements, mirroring how
app.documents.providers.base.DocumentProvider is the one interface every
document source implements.

Each monitor's check() is pure diffing logic: given a ticker and the
opaque `last_state` dict from its MonitoringJob row, fetch current data
(reusing app/providers/market.py or app/documents/providers/sec_edgar.py —
no new external API clients duplicated here) and return
(events, new_state). The scheduler (app/monitoring/scheduler.py) owns
persistence of new_state back onto the job row; check() itself never
touches the database — same discover()/fetch() separation-of-concerns
reasoning as DocumentProvider.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MonitorEvent:
    """One meaningful, detected change — not yet deduplicated or persisted.
    app.monitoring.alert_service.AlertService turns these into Alert rows,
    dropping any whose dedup_key already has a matching Alert."""

    event_type: str
    title: str
    description: str
    severity: str = "info"  # "info" | "warning" | "critical"
    dedup_key: str = ""
    data: dict = field(default_factory=dict)


class Monitor(ABC):
    monitor_type: str

    @abstractmethod
    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        """Returns (new_events, updated_state). Must not raise for ordinary
        "nothing changed" / "no data available" cases — only for genuine
        infrastructure failures the scheduler should log and back off on."""
        raise NotImplementedError
