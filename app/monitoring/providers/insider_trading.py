"""
Insider trading monitor — alerts on new insider buy/sell transactions
(dedup'd by Finnhub's own transaction identity: name + transactionDate +
share count, since the free-tier endpoint doesn't expose a stable numeric
transaction id).
"""
from app.core.config import get_settings
from app.providers.market import get_insider_transactions
from app.monitoring.providers.base import Monitor, MonitorEvent

settings = get_settings()


def _transaction_key(t: dict) -> str:
    return f"{t.get('name')}|{t.get('transactionDate')}|{t.get('share')}|{t.get('transactionCode')}"


class InsiderTradingMonitor(Monitor):
    monitor_type = "insider_trading"

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        transactions = await get_insider_transactions(ticker)
        if not transactions:
            return [], last_state

        seen_keys = set(last_state.get("seen_keys", []))
        events: list[MonitorEvent] = []
        new_keys: list[str] = []

        for t in transactions:
            key = _transaction_key(t)
            new_keys.append(key)
            if key in seen_keys or len(events) >= settings.monitoring_max_insider_alerts_per_run:
                continue

            change = t.get("change", 0) or 0
            action = "bought" if change > 0 else "sold" if change < 0 else "reported a transaction in"
            events.append(MonitorEvent(
                event_type="insider_transaction",
                title=f"{ticker}: {t.get('name', 'An insider')} {action} shares",
                description=f"{t.get('name', 'An insider')} {action} {abs(change):,} shares of {ticker} on {t.get('transactionDate', 'an unspecified date')}.",
                severity="info",
                dedup_key=f"insider:{ticker}:{key}",
                data=t,
            ))

        # First-ever poll: record history without alerting on all of it.
        if not last_state.get("seen_keys"):
            events = []

        updated_seen = list(dict.fromkeys(new_keys + list(seen_keys)))[:200]
        return events, {**last_state, "seen_keys": updated_seen}
