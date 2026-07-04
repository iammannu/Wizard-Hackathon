from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    environment: str = "development"

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

    # DB — SQLite by default, swap for Postgres when you need to scale
    database_url: str = "sqlite+aiosqlite:///./alphaforage.db"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
