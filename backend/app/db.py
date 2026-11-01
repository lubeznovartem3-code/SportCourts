"""Подключение к PostgreSQL и небольшие помощники для SQL-запросов.

Запросы пишутся на чистом SQL (sqlalchemy.text) — схема описана в миграциях.
ВАЖНО для драйвера asyncpg: параметр, который встречается в контексте без типа
(`:x IS NULL`, аргумент функции), нужно явно приводить: CAST(:x AS bigint).
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import Settings

logger = logging.getLogger("sportcourts.db")


def make_engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url
    connect_args: dict[str, Any] = {}
    if url.startswith("postgresql+asyncpg://"):
        connect_args = {"timeout": 5, "command_timeout": 30}
    elif url.startswith("postgresql+psycopg://"):
        connect_args = {"connect_timeout": 5}
    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_timeout=10,
        pool_recycle=1800,
        connect_args=connect_args,
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: одна сессия на запрос.

    Фиксацию изменений endpoint выполняет сам (`await db.commit()`) до возврата ответа,
    поэтому клиент никогда не получает «успех» до записи данных. Если endpoint завершился
    ошибкой, незафиксированные изменения откатываются при закрытии сессии.
    """
    async with request.app.state.sessionmaker() as session:
        try:
            yield session
        finally:
            await session.rollback()


# --------------------------------------------------------------------------- помощники
def _row(mapping: Any) -> dict[str, Any]:
    return dict(mapping)


async def q_all(db: AsyncSession, sql: str, **params: Any) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params)
    return [_row(m) for m in result.mappings().all()]


async def q_one(db: AsyncSession, sql: str, **params: Any) -> dict[str, Any] | None:
    result = await db.execute(text(sql), params)
    m = result.mappings().first()
    return _row(m) if m is not None else None


async def q_val(db: AsyncSession, sql: str, **params: Any) -> Any:
    result = await db.execute(text(sql), params)
    return result.scalar()


async def q_exec(db: AsyncSession, sql: str, **params: Any) -> int:
    result = await db.execute(text(sql), params)
    return result.rowcount or 0


def as_json(value: Any, default: Any = None) -> Any:
    """Драйверы по-разному возвращают json: строкой или уже разобранным объектом."""
    if value is None:
        return default
    if isinstance(value, (str, bytes)):
        return json.loads(value)
    return value


async def check_database(engine: AsyncEngine) -> tuple[bool, str | None]:
    """Проверяет подключение. Возвращает (ok, причина) без утечки секретов."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, type(exc).__name__


async def check_collation(engine: AsyncEngine) -> bool:
    """True, если регистронезависимый поиск работает для кириллицы."""
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 'Яблоко' ILIKE '%ябл%'"))
            return bool(res.scalar())
    except Exception:  # noqa: BLE001
        return True
