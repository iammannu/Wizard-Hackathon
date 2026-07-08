"""
Earnings monitor — alerts when a new quarterly period appears in Finnhub's
earnings-surprise history (i.e. the company just reported), classifying it
as a beat/miss/inline against the estimate.
"""
from app.providers.market import get_earnings
from app.monitoring.providers.base import Monitor, MonitorEvent

_BEAT_MISS_TOLERANCE = 0.01  # within 1% of estimate counts as "inline"


class EarningsMonitor(Monitor):
    monitor_type = "earnings"

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        reports = await get_earnings(ticker)
        if not reports:
            return [], last_state

        latest = reports[0]
        period = latest.get("period")
        if not period:
            return [], last_state

        last_seen_period = last_state.get("last_period")
        new_state = {**last_state, "last_period": period}

        if last_seen_period is None:
            # First-ever poll: record but don't alert on history that
            # predates monitoring.
            return [], new_state
        if period == last_seen_period:
            return [], new_state

        actual, estimate = latest.get("actual"), latest.get("estimate")
        classification = "inline"
        if actual is not None and estimate not in (None, 0):
            delta_pct = (actual - estimate) / abs(estimate)
            if delta_pct > _BEAT_MISS_TOLERANCE:
                classification = "beat"
            elif delta_pct < -_BEAT_MISS_TOLERANCE:
                classification = "miss"

        severity = "warning" if classification == "miss" else "info"
        event = MonitorEvent(
            event_type="earnings_report",
            title=f"{ticker} reported Q{period} earnings — {classification}",
            description=f"{ticker} reported EPS of {actual} vs. estimate {estimate} for period {period} ({classification}).",
            severity=severity,
            dedup_key=f"earnings:{ticker}:{period}",
            data={"period": period, "actual": actual, "estimate": estimate, "classification": classification},
        )
        return [event], new_state
