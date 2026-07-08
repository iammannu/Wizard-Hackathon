"""
News monitor — alerts on articles published since the last poll. Dedup is
by article id (Polygon news items carry a stable `id`); last_state tracks
the newest id/published timestamp seen so re-running the same poll twice in
quick succession (e.g. a manual "run now") doesn't re-alert on the same
articles.
"""
from app.core.config import get_settings
from app.providers.market import get_news
from app.monitoring.providers.base import Monitor, MonitorEvent

settings = get_settings()


class NewsMonitor(Monitor):
    monitor_type = "news"

    async def check(self, ticker: str, last_state: dict) -> tuple[list[MonitorEvent], dict]:
        articles = await get_news(ticker, limit=20)
        if not articles:
            return [], last_state

        seen_ids = set(last_state.get("seen_ids", []))
        events: list[MonitorEvent] = []
        new_ids: list[str] = []

        for article in articles:
            article_id = article.get("id") or article.get("article_url") or article.get("title")
            if not article_id:
                continue
            new_ids.append(str(article_id))
            if str(article_id) in seen_ids:
                continue
            if len(events) >= settings.monitoring_max_news_alerts_per_run:
                continue

            title = article.get("title", "Untitled")
            events.append(MonitorEvent(
                event_type="new_article",
                title=f"{ticker}: {title}",
                description=(article.get("description") or "")[:300],
                severity="info",
                dedup_key=f"news:{ticker}:{article_id}",
                data={"url": article.get("article_url"), "publisher": (article.get("publisher") or {}).get("name")},
            ))

        # First-ever poll: record what's on file but don't alert on the
        # entire backlog as if it all just happened.
        if not last_state.get("seen_ids"):
            events = []

        updated_seen = list(dict.fromkeys(new_ids + list(seen_ids)))[:200]  # cap growth, keep newest first
        return events, {**last_state, "seen_ids": updated_seen}
