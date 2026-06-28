"""
SQLite via SQLAlchemy async.
For production: swap database_url to postgresql+asyncpg://...
Schema is simple — just users + refresh tokens for auth.
No TimescaleDB, no per-service databases.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with SessionLocal() as session:
        yield session
