"""Служебные маршруты, формат ошибок, недоступность базы данных."""
import pytest

from .conftest import API, TEST_DB_URL, register, run_app

pytestmark = pytest.mark.anyio


async def test_health_and_ready(client):
    h = await client.get("/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json() == {"status": "ready", "database": True, "revision": "0002"}


async def test_unknown_route_and_method_use_error_format(client):
    r = await client.get(f"{API}/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = await client.delete(f"{API}/auth/me")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


async def test_malformed_json_is_422_not_500(client):
    r = await client.post(f"{API}/auth/login", content=b"{bad json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_request_body_limit(tmp_path, anyio_backend):
    async with run_app(tmp_path, max_upload_mb=1, max_request_mb=1) as c:
        r = await c.post(f"{API}/auth/login", content=b"x" * (2 * 1024 * 1024), headers={"content-type": "application/json"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


async def test_docs_hidden_in_production(tmp_path, anyio_backend):
    async with run_app(tmp_path, app_env="production") as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404


async def test_database_unavailable_gives_503_and_server_survives(tmp_path, anyio_backend):
    """База недоступна (неверный порт): сервер запускается, API отвечает понятным 503, а не падает."""
    bad_url = TEST_DB_URL.replace(":5432/", ":1/")
    assert bad_url != TEST_DB_URL
    async with run_app(tmp_path, truncate=False, db_url=bad_url) as c:
        assert (await c.get("/health")).status_code == 200                    # процесс жив
        ready = await c.get("/ready")
        assert ready.status_code == 503 and ready.json()["database"] is False
        r = await c.post(f"{API}/auth/login", json={"login": "someone", "password": "password123"})
        assert r.status_code == 503
        err = r.json()["error"]
        assert err["code"] == "database_unavailable" and "недоступен" in err["message"]
        r = await c.post(f"{API}/auth/register", json={"login": "newuser", "password": "password123"})
        assert r.status_code == 503
        r = await c.get(f"{API}/venues", headers={"Authorization": "Bearer abc.def.ghi"})
        assert r.status_code == 401                                           # токен проверяется без базы


async def test_database_outage_mid_flight_then_recovery(tmp_path, anyio_backend):
    """Соединения рвутся посреди работы — запросы получают 503, после возвращения базы всё работает."""
    from sqlalchemy import text
    async with run_app(tmp_path) as c:
        a = await register(c, "survivor")
        async with c.app.state.engine.connect() as admin_conn:                       # type: ignore[attr-defined]
            await admin_conn.execute(text("SELECT 1"))
        # принудительно завершаем все соединения приложения с базой
        from sqlalchemy.ext.asyncio import create_async_engine
        killer = create_async_engine(TEST_DB_URL, isolation_level="AUTOCOMMIT")
        async with killer.connect() as k:
            await k.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                 "WHERE datname = current_database() AND pid <> pg_backend_pid()"))
        await killer.dispose()
        r = await a.get("/auth/me")
        assert r.status_code in (200, 503)                                           # pre_ping мог уже переподключиться
        assert (await a.get("/auth/me")).status_code == 200                          # дальше всё работает
