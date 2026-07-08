"""
SQLite via SQLAlchemy async.
For production: swap database_url to postgresql+asyncpg://...
Schema is simple — just users + refresh tokens for auth.
No TimescaleDB, no per-service databases.
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()


def ensure_aware_utc(value: datetime) -> datetime:
    """SQLite's DateTime(timezone=True) does not round-trip tzinfo — a
    column written with an aware UTC datetime comes back naive once it's
    been through an actual INSERT/SELECT round trip (e.g. re-fetched in a
    new request's session), even though the column is declared
    timezone-aware. Every datetime this app ever writes is already UTC
    (datetime.now(timezone.utc), by convention, everywhere), so a naive
    value read back is safely assumed to already be UTC wall-clock time —
    this just re-attaches the tzinfo so Python-side comparisons against a
    fresh datetime.now(timezone.utc) don't raise TypeError. SQL-side WHERE
    clause comparisons (e.g. Model.next_run_at <= now) don't need this —
    both operands go through the same bind_processor there and compare
    correctly as-is; this is only for comparisons done in Python after a
    row has already been loaded."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from app.models.user import User, RefreshToken              # noqa: F401
    from app.models.workspace import Workspace, WorkspaceResearch  # noqa: F401
    from app.models.memory import (                              # noqa: F401
        ConversationMemory, WorkspaceMemory, CompanyMemory, ThesisMemory,
    )
    from app.models.monitoring import MonitoringJob, Alert          # noqa: F401
    from app.models.portfolio import (                               # noqa: F401
        Portfolio, PortfolioHolding, HoldingSnapshot, Watchlist, PortfolioActivity,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with SessionLocal() as session:
        yield session
