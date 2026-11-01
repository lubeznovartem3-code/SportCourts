"""Общие фикстуры тестов.

Запуск (из каталога backend, база должна быть пустой и отдельной от рабочей!):

    set TEST_DATABASE_URL=postgresql+asyncpg://sportcourts:ПАРОЛЬ@127.0.0.1:5432/sportcourts_test
    pytest

ВНИМАНИЕ: тесты стирают все данные в базе TEST_DATABASE_URL. Никогда не указывайте рабочую базу.
Миграции применяются автоматически (сначала откат до нуля, затем обновление до последней версии).
"""
from __future__ import annotations

import datetime as dt
import io
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import pytest
from PIL import Image
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
API = "/api/v1"

DATA_TABLES = (
    "audit_log, reports, notifications, messages, user_blocks, friend_requests, friendships, game_participants, "
    "games, player_reports, presence_checkins, moderator_requests, moderation_decisions, "
    "venue_change_proposal_sports, venue_change_proposals, venue_submission_sports, venue_submissions, "
    "venue_sports, venues, user_favorite_sports, user_sessions, users"
)


def _base_env() -> dict[str, str]:
    return {**os.environ, "DATABASE_URL": TEST_DB_URL, "SECRET_KEY": "test-secret-key-" + "x" * 32,
            "SPORTCOURTS_ENV_FILE": os.devnull}


def pytest_configure(config: pytest.Config) -> None:
    if not TEST_DB_URL:
        pytest.exit("Не задана TEST_DATABASE_URL (см. docstring в tests/conftest.py)", returncode=2)
    if os.environ.get("SC_STRICT_PARAMS") == "1":
        from tests import strict_params  # noqa: F401  (только для проверки с драйвером psycopg)


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    """Откат до нуля и обновление до последней версии: проверяет миграции в обе стороны."""
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, env=_base_env(),
                                capture_output=True, text=True)
        if result.returncode != 0:
            pytest.exit(f"alembic {' '.join(args)} завершился с ошибкой:\n{result.stdout}\n{result.stderr}", returncode=2)


@pytest.fixture(params=["asyncio"])
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@asynccontextmanager
async def run_app(tmp_path: Path, truncate: bool = True, db_url: str | None = None, **overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
    env = {
        "DATABASE_URL": db_url or TEST_DB_URL, "SECRET_KEY": "test-secret-key-" + "x" * 32, "APP_ENV": "development",
        "UPLOADS_DIR": str(tmp_path / "uploads"), "LOGS_DIR": str(tmp_path / "logs"), "DATA_DIR": str(tmp_path / "data"),
        "REGISTER_MAX_PER_IP": "1000", "PLAYER_REPORT_COOLDOWN_SECONDS": "0",
        **{k.upper(): str(v) for k, v in overrides.items()},
    }
    settings = load_settings(environ=env, env_file=os.devnull)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        if truncate:
            async with app.state.engine.begin() as conn:
                await conn.execute(text(f"TRUNCATE {DATA_TABLES} RESTART IDENTITY CASCADE"))
        transport = httpx.ASGITransport(app=app, client=("203.0.113.5", 40000), raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.app = app  # type: ignore[attr-defined]
            yield client


@pytest.fixture
async def client(tmp_path: Path, anyio_backend: str) -> AsyncIterator[httpx.AsyncClient]:
    async with run_app(tmp_path) as c:
        yield c


# ----------------------------------------------------------------------------- помощники
PASSWORD = "correct-horse-1"


class Actor:
    """Пользователь теста: заголовки авторизации и данные профиля."""

    def __init__(self, client: httpx.AsyncClient, token: str, user: dict[str, Any], password: str) -> None:
        self.client, self.token, self.user, self.password = client, token, user, password
        self.id: int = user["id"]
        self.login: str = user["login"]

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self.client.get(API + url, headers=self.h, **kw)

    async def post(self, url: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.client.post(API + url, headers=self.h, json=json, **kw)

    async def put(self, url: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.client.put(API + url, headers=self.h, json=json, **kw)

    async def patch(self, url: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.client.patch(API + url, headers=self.h, json=json, **kw)

    async def delete(self, url: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.client.request("DELETE", API + url, headers=self.h, json=json, **kw)


async def sql(client: httpx.AsyncClient, query: str, **params: Any) -> list[Any]:
    """Выполняет SQL напрямую в тестовой базе (для подготовки данных и проверок)."""
    async with client.app.state.engine.begin() as conn:  # type: ignore[attr-defined]
        result = await conn.execute(text(query), params)
        return list(result.all()) if result.returns_rows else []


async def register(client: httpx.AsyncClient, login: str, password: str = PASSWORD, **extra: Any) -> Actor:
    r = await client.post(f"{API}/auth/register", json={"login": login, "password": password, **extra})
    assert r.status_code == 201, r.text
    data = r.json()
    return Actor(client, data["token"], data["user"], password)


async def make_role(client: httpx.AsyncClient, actor: Actor, role: str) -> Actor:
    await sql(client, "UPDATE users SET role = :r WHERE id = :id", r=role, id=actor.id)
    return actor


async def admin_actor(client: httpx.AsyncClient, login: str = "admin") -> Actor:
    return await make_role(client, await register(client, login), "admin")


def venue_payload(name: str = "Хамовники Арена", **over: Any) -> dict[str, Any]:
    body = {"name": name, "address": "Москва, ул. Лужники, 24", "latitude": 55.7158, "longitude": 37.5538,
            "venue_type": "outdoor", "sport_ids": [2], "description": "Открытая площадка",
            "work_hours": "08:00 - 23:00", "cost_info": "Бесплатно"}
    body.update(over)
    return body


async def create_venue(client: httpx.AsyncClient, admin: Actor, **over: Any) -> dict[str, Any]:
    body = venue_payload(**over)
    body.setdefault("force", True)
    r = await admin.post("/admin/venues", body)
    assert r.status_code == 201, r.text
    return r.json()


def png_bytes(size: tuple[int, int] = (300, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def future(hours: float = 3) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)).isoformat()
