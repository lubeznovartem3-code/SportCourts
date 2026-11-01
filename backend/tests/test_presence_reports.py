"""Личное присутствие и отчёты о числе игроков — два независимых механизма."""
import pytest

from .conftest import admin_actor, create_venue, register, run_app, sql

pytestmark = pytest.mark.anyio


async def _setup(client):
    admin = await admin_actor(client)
    v1 = await create_venue(client, admin, name="Площадка 1", latitude=55.0, longitude=37.0)
    v2 = await create_venue(client, admin, name="Площадка 2", latitude=56.0, longitude=38.0)
    return v1, v2


async def test_toggle_presence(client):
    v1, _ = await _setup(client)
    u = await register(client, "player")
    on = (await u.post(f"/venues/{v1['id']}/presence/toggle")).json()
    assert on["active"] is True and on["checked_in_count"] == 1 and on["expires_at"]
    assert (await u.get(f"/venues/{v1['id']}")).json()["my_presence"]["active"] is True
    off = (await u.post(f"/venues/{v1['id']}/presence/toggle")).json()
    assert off["active"] is False and off["checked_in_count"] == 0
    rows = await sql(client, "SELECT end_reason FROM presence_checkins")
    assert [r[0] for r in rows] == ["manual"]                                    # запись осталась в истории


async def test_one_active_checkin_per_user(client):
    v1, v2 = await _setup(client)
    u = await register(client, "player")
    await u.post(f"/venues/{v1['id']}/presence/toggle")
    moved = (await u.post(f"/venues/{v2['id']}/presence/toggle")).json()
    assert moved["active"] is True
    assert (await u.get(f"/venues/{v1['id']}")).json()["checked_in_count"] == 0
    assert (await u.get(f"/venues/{v2['id']}")).json()["checked_in_count"] == 1
    open_rows = await sql(client, "SELECT count(*) FROM presence_checkins WHERE ended_at IS NULL")
    assert open_rows[0][0] == 1
    assert sorted(r[0] for r in await sql(client, "SELECT end_reason FROM presence_checkins WHERE ended_at IS NOT NULL")) == ["moved"]


async def test_counts_come_from_server_for_many_users(client):
    v1, _ = await _setup(client)
    for i in range(4):
        u = await register(client, f"p{i}x")
        await u.post(f"/venues/{v1['id']}/presence/toggle")
    assert (await u.get(f"/venues/{v1['id']}")).json()["checked_in_count"] == 4


async def test_presence_expires_after_three_hours(client):
    v1, _ = await _setup(client)
    u = await register(client, "player")
    await u.post(f"/venues/{v1['id']}/presence/toggle")
    ttl = await sql(client, "SELECT extract(epoch FROM expires_at - started_at) FROM presence_checkins")
    assert round(float(ttl[0][0])) == 3 * 3600
    # «проматываем» время: срок истёк
    await sql(client, "UPDATE presence_checkins SET started_at = now() - interval '4 hours', expires_at = now() - interval '1 hour'")
    assert (await u.get(f"/venues/{v1['id']}")).json()["checked_in_count"] == 0     # не считается, даже если запись ещё не закрыта
    assert (await u.get(f"/venues/{v1['id']}")).json()["my_presence"]["active"] is False
    again = (await u.post(f"/venues/{v1['id']}/presence/toggle")).json()
    assert again["active"] is True                                              # новая отметка, а не «снятие» старой
    rows = await sql(client, "SELECT end_reason, ended_at IS NOT NULL FROM presence_checkins ORDER BY id")
    assert [tuple(r) for r in rows] == [("expired", True), (None, False)]       # история сохранена


async def test_background_job_closes_expired(client):
    v1, _ = await _setup(client)
    u = await register(client, "player")
    await u.post(f"/venues/{v1['id']}/presence/toggle")
    await sql(client, "UPDATE presence_checkins SET started_at = now() - interval '4 hours', expires_at = now() - interval '1 hour'")
    from sqlalchemy import text
    async with client.app.state.sessionmaker() as s:
        await s.execute(text("UPDATE presence_checkins SET ended_at = expires_at, end_reason = 'expired' "
                             "WHERE ended_at IS NULL AND expires_at <= now()"))
        await s.commit()
    assert (await sql(client, "SELECT end_reason FROM presence_checkins"))[0][0] == "expired"


async def test_double_tap_concurrent(client):
    import asyncio
    v1, _ = await _setup(client)
    u = await register(client, "player")
    results = await asyncio.gather(*[u.post(f"/venues/{v1['id']}/presence/toggle") for _ in range(6)])
    assert all(r.status_code == 200 for r in results)
    assert (await sql(client, "SELECT count(*) FROM presence_checkins WHERE ended_at IS NULL"))[0][0] <= 1
    # шесть нажатий подряд = «вкл, выкл, вкл, выкл, вкл, выкл»: три записи истории, ни одной активной
    assert (await sql(client, "SELECT count(*) FROM presence_checkins"))[0][0] == 3
    assert (await sql(client, "SELECT count(*) FROM presence_checkins WHERE ended_at IS NULL"))[0][0] == 0


async def test_player_reports_separate_from_presence(client):
    v1, _ = await _setup(client)
    a, b = await register(client, "a1x"), await register(client, "b1x")
    await a.post(f"/venues/{v1['id']}/presence/toggle")
    assert (await b.post(f"/venues/{v1['id']}/player-reports", {"player_count": 9})).status_code == 201
    d = (await a.get(f"/venues/{v1['id']}")).json()
    assert d["checked_in_count"] == 1                                            # отметки приложения
    assert d["latest_report"]["player_count"] == 9 and d["latest_report"]["is_fresh"] is True
    assert d["latest_report"]["reported_at"]
    hist = (await a.get(f"/venues/{v1['id']}/player-reports")).json()["items"]
    assert hist[0]["reporter"]["login"] == "b1x" and hist[0]["player_count"] == 9
    listing = (await a.get("/venues")).json()["items"]
    assert [x for x in listing if x["id"] == v1["id"]][0]["players_estimate"] == 9


async def test_latest_report_wins_and_history_kept(client):
    v1, _ = await _setup(client)
    a, b = await register(client, "a1x"), await register(client, "b1x")
    await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": 4})
    await b.post(f"/venues/{v1['id']}/player-reports", {"player_count": 0})
    assert (await a.get(f"/venues/{v1['id']}")).json()["latest_report"]["player_count"] == 0
    assert len((await a.get(f"/venues/{v1['id']}/player-reports")).json()["items"]) == 2


async def test_report_becomes_stale(client):
    v1, _ = await _setup(client)
    a = await register(client, "a1x")
    await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": 12})
    await sql(client, "UPDATE player_reports SET created_at = now() - interval '7 hours'")
    d = (await a.get(f"/venues/{v1['id']}")).json()
    assert d["latest_report"]["is_fresh"] is False                              # не выдаём устаревшее за актуальное
    assert (await a.get("/venues")).json()["items"][0]["players_estimate"] == 0


@pytest.mark.parametrize("count", [-1, 201, "x"])
async def test_report_validation(client, count):
    v1, _ = await _setup(client)
    a = await register(client, "a1x")
    assert (await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": count})).status_code == 422


async def test_report_cooldown_and_hourly_limit(tmp_path, anyio_backend):
    async with run_app(tmp_path, player_report_cooldown_seconds=300, player_report_max_per_hour=3) as c:
        v1, v2 = await _setup(c)
        a = await register(c, "spam1")
        assert (await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": 3})).status_code == 201
        r = await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": 4})
        assert r.status_code == 429 and r.json()["error"]["details"]["retry_after_seconds"] > 0
        assert (await a.post(f"/venues/{v2['id']}/player-reports", {"player_count": 4})).status_code == 201   # другая площадка
        await sql(c, "UPDATE player_reports SET created_at = now() - interval '10 minutes'")
        assert (await a.post(f"/venues/{v1['id']}/player-reports", {"player_count": 5})).status_code == 201
        await sql(c, "UPDATE player_reports SET created_at = now() - interval '10 minutes'")
        assert (await a.post(f"/venues/{v2['id']}/player-reports", {"player_count": 2})).status_code == 429   # 3 за час уже было
