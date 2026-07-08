"""
Analyst rating monitor — alerts only on a *consensus transition*
(e.g. hold -> buy), not on every poll that happens to still say "buy".
Polling cadence is already coarse (Settings.monitoring_poll_interval_analyst_rating,
default 12h) since consensus rarely moves faster than that.
"""
from app.providers.market import get_analyst
from app.monitoring.providers.base import Monitor, MonitorEvent

_RANK = {"sell": 0, "hold": 1, "buy": 2}


class AnalystRatingMonitor(Monitor):
    monitor_type = "analyst_rating"

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        analyst = await get_analyst(ticker)
        if not analyst or not analyst.get("consensus"):
            return [], last_state

        consensus = analyst["consensus"]
        previous = last_state.get("consensus")
        new_state = {**last_state, "consensus": consensus}

        if previous is None or previous == consensus:
            return [], new_state

        prev_rank, new_rank = _RANK.get(previous, 1), _RANK.get(consensus, 1)
        direction = "upgrade" if new_rank > prev_rank else "downgrade"
        event = MonitorEvent(
            event_type=f"rating_{direction}",
            title=f"{ticker} analyst consensus {direction}d: {previous} → {consensus}",
            description=f"Analyst consensus for {ticker} moved from '{previous}' to '{consensus}'.",
            severity="warning" if direction == "downgrade" else "info",
            dedup_key=f"analyst:{ticker}:{previous}->{consensus}",
            data={"previous_consensus": previous, "new_consensus": consensus, "detail": analyst.get("detail", {})},
        )
        return [event], new_state
