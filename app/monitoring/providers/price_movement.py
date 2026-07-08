"""
Price movement monitor — alerts when a ticker moves more than
Settings.monitoring_price_alert_threshold_pct since the last poll's
checkpoint price (not just vs. the prior day's close, which get_quote's
change_pct already is — that alone would double-alert every day the market
is simply volatile). last_state carries the checkpoint forward so the
"meaningful change" is always measured from what this monitor last saw.
"""
from app.core.config import get_settings
from app.providers.market import get_quote
from app.monitoring.providers.base import Monitor, MonitorEvent

settings = get_settings()


class PriceMovementMonitor(Monitor):
    monitor_type = "price_movement"

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        quote = await get_quote(ticker)
        if not quote or not quote.get("price"):
            return [], last_state

        price = quote["price"]
        checkpoint = last_state.get("checkpoint_price")
        new_state = {**last_state, "checkpoint_price": price}

        if checkpoint is None:
            # First observation — nothing to compare against yet.
            return [], new_state

        pct_change = (price - checkpoint) / checkpoint * 100 if checkpoint else 0.0
        if abs(pct_change) < settings.monitoring_price_alert_threshold_pct:
            return [], new_state

        direction = "up" if pct_change > 0 else "down"
        severity = "critical" if abs(pct_change) >= settings.monitoring_price_alert_threshold_pct * 2 else "warning"

        event = MonitorEvent(
            event_type="price_movement",
            title=f"{ticker} moved {direction} {abs(pct_change):.1f}%",
            description=f"{ticker} is now ${price:.2f}, {pct_change:+.1f}% from the last checkpoint of ${checkpoint:.2f}.",
            severity=severity,
            dedup_key=f"price:{ticker}:{price:.2f}",
            data={"price": price, "checkpoint_price": checkpoint, "pct_change": round(pct_change, 2)},
        )
        return [event], new_state
