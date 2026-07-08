"""
Alembic async environment for AlphaForage.

Reads DATABASE_URL from app settings — same source as the FastAPI app itself.
Supports both SQLite (dev) and PostgreSQL (production) without code changes.

Extension points:
  - Add new model imports below as new phases introduce models
  - Switch to postgresql+asyncpg:// in .env when scaling; no code changes needed here
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Pull in our DeclarativeBase so autogenerate can inspect all registered models
from app.core.database import Base  # noqa: F401
from app.core.config import get_settings

# Import all models so their tables are registered on Base.metadata.
# Add new model modules here as new phases are implemented.
from app.models import user as _user_models            # noqa: F401
from app.models import workspace as _workspace_models  # noqa: F401
from app.models import thesis as _thesis_models        # noqa: F401
from app.documents.models import document as _document_models  # noqa: F401
from app.documents.models import chunk as _chunk_models        # noqa: F401
from app.documents.models import entity as _entity_models      # noqa: F401
from app.documents.models import citation as _citation_models  # noqa: F401
from app.documents.models import embedding as _embedding_models  # noqa: F401

config = context.config

# Honour the logging config in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with the value from app settings — single source of truth.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required).

    Useful for generating SQL scripts for DBA review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # render_as_batch enables ALTER TABLE emulation for SQLite
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # render_as_batch enables ALTER TABLE emulation for SQLite, harmless on Postgres
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync connection bridge."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
