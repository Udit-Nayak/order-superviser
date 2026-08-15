from collections.abc import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


def _normalize_asyncpg_url(raw_url: str) -> str:
    if not raw_url:
        raise RuntimeError(
            "SUPABASE_DB_URL is missing. Add the Supabase Postgres connection string to .env."
        )
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise RuntimeError("SUPABASE_DB_URL must be a PostgreSQL connection string.")


DATABASE_URL = _normalize_asyncpg_url(settings.supabase_db_url)
_db_host = make_url(DATABASE_URL).host or ""
_connect_args = {} if _db_host in {"localhost", "127.0.0.1"} else {"ssl": "require"}

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
