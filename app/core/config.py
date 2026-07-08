from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    environment: str = "development"

    # CORS — comma-separated list of allowed origins, e.g.
    # "https://app.alphaforage.com,https://alphaforage.com". Defaults to "*"
    # for local/dev convenience (matches this app's existing zero-config
    # dev experience); set this explicitly in production .env so the API
    # only accepts requests from your real frontend origin(s), not any site.
    cors_allowed_origins: str = "*"

    # Auth
    secret_key: str = "change-me-in-production-min-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h for dev convenience

    # Market data
    polygon_api_key: str = ""
    finnhub_api_key: str = ""

    # AI
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"

    # Research providers — Tier 3 verification/freshness layer only.
    # Document Intelligence (app/documents/) is the primary knowledge source;
    # these supplement it, they do not replace it. See app/documents/providers/.
    youcom_api_key: str = ""
    tavily_api_key: str = ""

    # Document Intelligence — SEC EDGAR (Tier 1 primary source)
    # SEC requires a compliant User-Agent identifying the requester on every
    # call (https://www.sec.gov/os/webmaster-faq#developers) — format:
    # "Company/App Name contact@example.com". Requests are refused, not sent
    # with a placeholder, if this is left empty — silently violating SEC's
    # fair-access policy is worse than failing loudly. Set a real one in .env
    # before ingesting in production.
    sec_edgar_user_agent: str = ""

    # Semantic Retrieval Engine — embedding providers (app/documents/embeddings/)
    # "openai" is the default and the only one runnable out of the box today.
    # "voyage" needs voyage_api_key set. "local" needs `pip install
    # sentence-transformers` — not a core requirement, see requirements.txt.
    embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-3"
    local_embedding_model: str = "all-MiniLM-L6-v2"

    # Semantic Retrieval Engine — vector store (app/documents/retrieval/)
    # "sqlite" (brute-force cosine over document_embeddings) is the active
    # default — zero new infra. faiss/chroma/pinecone/pgvector are fully coded
    # behind the same VectorStore interface but need their SDK installed (and,
    # for pgvector, a postgresql database_url) before they're selectable.
    vector_store_provider: str = "sqlite"
    faiss_index_path: str = "./data/faiss_index"
    chroma_persist_dir: str = "./data/chroma"
    pinecone_api_key: str = ""
    pinecone_index_name: str = "alphaforage-chunks"

    # Retrieval tuning
    embedding_batch_size: int = 32
    retrieval_top_k_default: int = 8
    retrieval_context_max_tokens: int = 4000

    # Evidence Engine 2.0 (app/documents/evidence/) — scoring weights, one
    # flat field per factor rather than a nested dict, matching this file's
    # existing flat-settings convention. Defaults sum to 1.0; EvidenceScore.overall
    # is a weighted sum so changing these changes ranking, not just display.
    evidence_weight_semantic_similarity: float = 0.30
    evidence_weight_keyword_overlap: float = 0.15
    evidence_weight_section_importance: float = 0.10
    evidence_weight_recency: float = 0.10
    evidence_weight_authority: float = 0.10
    evidence_weight_source_quality: float = 0.10
    evidence_weight_completeness: float = 0.10
    evidence_weight_citation_density: float = 0.05

    # Evidence Engine 2.0 — pipeline thresholds/caps
    evidence_dedupe_threshold: float = 0.95   # cosine similarity above which two evidence items are near-duplicates
    evidence_conflict_threshold: float = 0.75  # cosine similarity above which two evidence items are "same topic" and checked for contradiction
    evidence_min_confidence: float = 0.0       # evidence below this overall score is dropped before claim building
    evidence_max_returned: int = 20            # cap on Evidence items in the final EvidencePack
    evidence_max_claims: int = 10              # cap on Claims generated per EvidencePack
    evidence_recency_decay_years: float = 5.0  # a document this many years old scores ~0 on recency

    # AI Memory (Milestone 3, app/memory/) — persistent cross-session research
    # memory. Reuses the Evidence Engine's embedding provider/model
    # (Settings.embedding_provider above) rather than a separate one — same
    # vector space, no second provider to configure.
    memory_dedup_threshold: float = 0.92     # cosine similarity above which a new memory item reinforces an existing one instead of creating a new row
    memory_contradiction_threshold: float = 0.80  # cosine similarity above which two same-type memory items are checked for contradiction
    memory_min_confidence: float = 0.35      # extracted memory items below this confidence are dropped before persisting
    memory_recall_top_k: int = 6             # default number of memory items returned to agents per query
    memory_max_extracted_per_session: int = 24  # cap on memory candidates extracted from one research run
    memory_confidence_decay_per_day: float = 0.0015  # small daily decay applied at recall time so stale, unreinforced memory naturally loses influence
    memory_company_promotion_min_confidence: float = 0.6  # WorkspaceMemory items must clear this (after reinforcement) to roll up into cross-workspace CompanyMemory

    # Monitoring & Alerts (Milestone 4, app/monitoring/) — one MonitoringJob
    # per (ticker, monitor_type), polled by a single in-process scheduler
    # loop (same asyncio.create_task pattern as the embedding worker, no new
    # infra). Poll intervals are deliberately different per source: filings/
    # earnings/analyst-rating/insider-trading change rarely (hours-to-days),
    # price/news change constantly but are cheap, cache-backed calls.
    monitoring_tick_interval_seconds: int = 60          # how often the scheduler checks which jobs are due
    monitoring_poll_interval_sec_filing: int = 21600    # 6h
    monitoring_poll_interval_earnings: int = 86400       # 24h
    monitoring_poll_interval_news: int = 1800            # 30m
    monitoring_poll_interval_insider_trading: int = 86400  # 24h
    monitoring_poll_interval_price_movement: int = 900   # 15m
    monitoring_poll_interval_analyst_rating: int = 43200  # 12h

    monitoring_price_alert_threshold_pct: float = 5.0    # abs % move vs prior close that counts as "meaningful"
    monitoring_max_news_alerts_per_run: int = 5          # cap per-ticker news alerts in one poll (avoid a burst flooding the feed)
    monitoring_max_insider_alerts_per_run: int = 5

    # Portfolio Intelligence (Milestone 5, app/portfolio/) — position health
    # score weights, one flat field per factor (same convention as the
    # Evidence Engine's evidence_weight_* fields above). Defaults sum to 1.0.
    health_weight_evidence_quality: float = 0.15
    health_weight_alert_severity: float = 0.15
    health_weight_valuation: float = 0.15
    health_weight_analyst_revisions: float = 0.10
    health_weight_earnings_risk: float = 0.10
    health_weight_insider_activity: float = 0.10
    health_weight_sentiment: float = 0.10
    health_weight_thesis_confidence: float = 0.15

    portfolio_risk_volatility_high_pct: float = 40.0   # annualized vol at/above this scores near-zero on the risk factor
    portfolio_concentration_hhi_moderate: float = 1500.0  # traditional HHI bands (0-10000 scale)
    portfolio_concentration_hhi_high: float = 2500.0
    portfolio_summary_lookback_hours: int = 24

    # DB — SQLite by default, swap for Postgres when you need to scale
    database_url: str = "sqlite+aiosqlite:///./alphaforage.db"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parses cors_allowed_origins into the list shape CORSMiddleware
        expects. "*" stays a single-item ["*"] wildcard; anything else is
        split on commas and trimmed."""
        raw = self.cors_allowed_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
