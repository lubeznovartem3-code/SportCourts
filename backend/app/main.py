"""Точка входа FastAPI: создание приложения, жизненный цикл, служебные маршруты."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__
from .config import Settings, load_settings
from .db import check_collation, check_database, make_engine, make_sessionmaker
from .errors import error_body, register_exception_handlers
from .files import FileStore
from .logging_setup import setup_logging
from .ratelimit import SlidingWindowLimiter
from .routers import admin, auth, games, social, users, venue_flow, venues

logger = logging.getLogger("sportcourts")
API_PREFIX = "/api/v1"
HEAD_REVISION = "0002"


class BodySizeLimitMiddleware:
    """Отклоняет запросы, чьё тело больше лимита (по заголовку Content-Length и по фактическому объёму)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        declared = headers.get(b"content-length")
        too_big = JSONResponse(
            status_code=413, content=error_body("payload_too_large", "Слишком большой запрос"))
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await too_big(scope, receive, send)
                    return
            except ValueError:
                pass
        received = 0
        exceeded = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        started = False

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal started
            if exceeded and not started:
                return  # ответ приложения подавляем, отправим 413 ниже
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
        if exceeded and not started:
            await too_big(scope, receive, send)


async def _background_loop(app: FastAPI) -> None:
    """Периодические задачи: закрытие просроченных отметок, очистка черновиков, контроль диска."""
    settings: Settings = app.state.settings
    tick = 0
    while True:
        try:
            async with app.state.sessionmaker() as session:
                res = await session.execute(text(
                    "UPDATE presence_checkins SET ended_at = expires_at, end_reason = 'expired' "
                    "WHERE ended_at IS NULL AND expires_at <= now()"))
                await session.commit()
                if res.rowcount:
                    logger.info("Закрыто просроченных отметок присутствия: %s", res.rowcount)
                if tick % 60 == 0:  # раз в час
                    await session.execute(text("DELETE FROM user_sessions WHERE expires_at < now() - interval '7 days' "
                                               "OR revoked_at < now() - interval '7 days'"))
                    await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка фоновой задачи (база недоступна?): %s", type(exc).__name__)
        if tick % 60 == 0:
            try:
                removed = await asyncio.to_thread(app.state.store.cleanup_staging, settings.staging_ttl_hours)
                if removed:
                    logger.info("Удалено устаревших черновиков фото: %s", removed)
                free_gb = shutil.disk_usage(settings.uploads_path).free / 1024 ** 3
                if free_gb < settings.min_free_disk_gb:
                    logger.warning("МАЛО МЕСТА НА ДИСКЕ: свободно %.1f ГБ (порог %.1f ГБ)", free_gb, settings.min_free_disk_gb)
            except Exception:  # noqa: BLE001
                logger.exception("Ошибка обслуживания файлов")
        tick += 1
        await asyncio.sleep(60)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_file = setup_logging(settings.logs_path, settings.log_level, settings.log_max_mb, settings.log_backup_count)
        logger.info("Запуск SportCourts %s (лог: %s)", __version__, log_file)
        app.state.settings = settings
        app.state.store = FileStore(settings.uploads_path)
        app.state.limiter = SlidingWindowLimiter()
        app.state.engine = make_engine(settings)
        app.state.sessionmaker = make_sessionmaker(app.state.engine)
        ok, reason = await check_database(app.state.engine)
        if ok:
            logger.info("Соединение с базой данных установлено")
            if not await check_collation(app.state.engine):
                logger.warning("База данных не различает регистр кириллицы (поиск будет неточным). См. docs/POSTGRESQL.md")
        else:
            logger.error("НЕТ СОЕДИНЕНИЯ С БАЗОЙ ДАННЫХ (%s). Сервер запущен, но API вернёт 503, пока база недоступна.", reason)
        task = asyncio.create_task(_background_loop(app))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await app.state.engine.dispose()
            logger.info("SportCourts остановлен")

    app = FastAPI(
        title="SportCourts API", version=__version__, lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
    )
    # состояние нужно и до старта lifespan (например, в тестах без lifespan)
    app.state.settings = settings
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_mb * 1024 * 1024)
    register_exception_handlers(app)

    for module in (auth, users, venues, venue_flow, games, social, admin):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/health", tags=["service"])
    async def health() -> dict[str, str]:
        """Сервер запущен (без проверки базы). Приложение использует это для проверки адреса."""
        return {"status": "ok", "service": "sportcourts", "version": __version__}

    @app.get("/ready", tags=["service"])
    async def ready(request: Request) -> JSONResponse:
        ok, reason = await check_database(request.app.state.engine)
        migrated = None
        if ok:
            try:
                async with request.app.state.engine.connect() as conn:
                    migrated = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
            except Exception:  # noqa: BLE001
                migrated = None
        if not ok:
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": False})
        if migrated != HEAD_REVISION:
            return JSONResponse(status_code=503, content={
                "status": "migrations_required", "database": True, "revision": migrated, "expected": HEAD_REVISION})
        return JSONResponse(content={"status": "ready", "database": True, "revision": migrated})

    @app.get("/media/{kind}/{filename}", tags=["service"], include_in_schema=False)
    async def media(kind: str, filename: str, request: Request):
        path: Path | None = request.app.state.store.resolve(kind, filename)
        if path is None:
            return JSONResponse(status_code=404, content=error_body("not_found", "Файл не найден"))
        return FileResponse(path, media_type="image/jpeg", headers={
            "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})

    return app
