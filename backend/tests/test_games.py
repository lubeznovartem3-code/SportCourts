"""Открытые игры: создание, вступление, лимит мест, выход, закрытие, конкурентность."""
import asyncio

import pytest

from .conftest import admin_actor, create_venue, future, register, run_app, sql

pytestmark = pytest.mark.anyio


async def _venue(client):
    admin = await admin_actor(client)
    return await create_venue(client, admin)


def game_body(venue, **over):
    body = {"venue_id": venue, "title": "Вечерний баскетбол", "starts_at": future(3), "max_players": 4}
    body.update(over)
    return body


async def test_create_game_organizer_takes_a_slot(client):
    v = await _venue(client)
    org = await register(client, "organizer")
    r = await org.post("/games", game_body(v["id"]))
    assert r.status_code == 201
    g = r.json()
    assert g["participants_count"] == 1 and g["free_slots"] == 3 and g["is_organizer"] and g["joined"]
    assert g["participants"][0]["is_organizer"] and g["participants"][0]["user"]["login"] == "organizer"
    assert g["venue"]["name"] == "Хамовники Арена" and g["venue"]["sports"][0]["name"] == "Баскетбол"


@pytest.mark.parametrize("over,status", [
    ({"max_players": 1}, 422), ({"max_players": 101}, 422), ({"title": "  "}, 422),
    ({"starts_at": "2020-01-01T10:00:00+00:00"}, 422), ({"starts_at": "2030-01-01T10:00:00"}, 422),
    ({"venue_id": 999}, 404),
])
async def test_create_game_validation(client, over, status):
    v = await _venue(client)
    org = await register(client, "organizer")
    body = game_body(v["id"], **over)
    assert (await org.post("/games", body)).status_code == status


async def test_join_leave_and_limit(client):
    v = await _venue(client)
    org = await register(client, "organizer")
    gid = (await org.post("/games", game_body(v["id"], max_players=3))).json()["id"]
    p1, p2, p3 = [await register(client, n) for n in ("pl1x", "pl2x", "pl3x")]
    assert (await p1.post(f"/games/{gid}/join")).json()["participants_count"] == 2
    assert (await p1.post(f"/games/{gid}/join")).status_code == 409             # уже участвует
    assert (await p2.post(f"/games/{gid}/join")).json()["free_slots"] == 0
    full = await p3.post(f"/games/{gid}/join")
    assert full.status_code == 409 and full.json()["error"]["code"] == "game_full"
    assert (await p1.post(f"/games/{gid}/leave")).status_code == 200            # место освободилось
    assert (await p3.post(f"/games/{gid}/join")).status_code == 200
    assert (await p1.post(f"/games/{gid}/leave")).status_code == 409            # не участник
    assert (await org.post(f"/games/{gid}/leave")).json()["error"]["code"] == "organizer_cannot_leave"


async def test_concurrent_joins_never_exceed_limit(client):
    v = await _venue(client)
    org = await register(client, "organizer")
    gid = (await org.post("/games", game_body(v["id"], max_players=5))).json()["id"]
    players = [await register(client, f"racer{i:02d}") for i in range(20)]
    results = await asyncio.gather(*[p.post(f"/games/{gid}/join") for p in players])
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 4 and codes.count(409) == 16, codes               # 5 мест, одно занято организатором
    assert all(r.json()["error"]["code"] == "game_full" for r in results if r.status_code == 409)
    count = (await sql(client, "SELECT count(*) FROM game_participants WHERE game_id = :g", g=gid))[0][0]
    assert count == 5


async def test_database_guard_blocks_overflow_even_without_app_checks(client):
    """Страховка на уровне БД: прямой INSERT сверх лимита отвергается триггером."""
    v = await _venue(client)
    org = await register(client, "organizer")
    gid = (await org.post("/games", game_body(v["id"], max_players=2))).json()["id"]
    p1, p2 = await register(client, "pl1x"), await register(client, "pl2x")
    await sql(client, "INSERT INTO game_participants (game_id, user_id) VALUES (:g, :u)", g=gid, u=p1.id)
    with pytest.raises(Exception) as exc:
        await sql(client, "INSERT INTO game_participants (game_id, user_id) VALUES (:g, :u)", g=gid, u=p2.id)
    assert "game_full" in str(exc.value)


async def test_cancel_and_finish_by_organizer_only(client):
    v = await _venue(client)
    org, other = await register(client, "organizer"), await register(client, "other1")
    g1 = (await org.post("/games", game_body(v["id"]))).json()["id"]
    g2 = (await org.post("/games", game_body(v["id"], title="Вторая"))).json()["id"]
    assert (await other.post(f"/games/{g1}/cancel")).status_code == 403
    assert (await other.post(f"/games/{g1}/finish")).status_code == 403
    assert (await org.post(f"/games/{g1}/cancel")).json()["status"] == "cancelled"
    assert (await org.post(f"/games/{g2}/finish")).json()["status"] == "finished"
    assert (await org.post(f"/games/{g1}/finish")).status_code == 409           # уже закрыта
    assert (await other.post(f"/games/{g1}/join")).json()["error"]["code"] == "game_closed"
    # исчезают из активных списков, остаются в истории
    assert (await other.get("/games")).json()["items"] == []
    hist = (await org.get("/games", params={"scope": "history"})).json()["items"]
    assert sorted(g["status"] for g in hist) == ["cancelled", "finished"]
    assert (await org.get("/games", params={"scope": "mine"})).json()["items"] == []


async def test_lists_and_filters(client):
    admin = await admin_actor(client)
    v1 = await create_venue(client, admin, name="В1", latitude=55.0, longitude=37.0)
    v2 = await create_venue(client, admin, name="В2", latitude=56.0, longitude=38.0)
    org, p = await register(client, "organizer"), await register(client, "player")
    a = (await org.post("/games", game_body(v1["id"], starts_at=future(5), title="Позже"))).json()["id"]
    b = (await org.post("/games", game_body(v2["id"], starts_at=future(2), title="Раньше"))).json()["id"]
    items = (await p.get("/games")).json()["items"]
    assert [g["title"] for g in items] == ["Раньше", "Позже"]                   # по времени начала
    assert [g["id"] for g in (await p.get("/games", params={"venue_id": v1["id"]})).json()["items"]] == [a]
    assert (await p.get(f"/venues/{v1['id']}")).json()["open_games_count"] == 1
    await p.post(f"/games/{b}/join")
    assert [g["id"] for g in (await p.get("/games", params={"scope": "mine"})).json()["items"]] == [b]
    assert [g["joined"] for g in (await p.get("/games")).json()["items"]] == [True, False]


async def test_stale_open_games_leave_active_list(client):
    v = await _venue(client)
    org = await register(client, "organizer")
    gid = (await org.post("/games", game_body(v["id"]))).json()["id"]
    await sql(client, "UPDATE games SET starts_at = now() - interval '2 days'")
    assert (await org.get("/games")).json()["items"] == []
    assert [g["id"] for g in (await org.get("/games", params={"scope": "history"})).json()["items"]] == [gid]
    late = await register(client, "late1")
    assert (await late.post(f"/games/{gid}/join")).json()["error"]["code"] == "game_over"
    assert (await org.post(f"/games/{gid}/finish")).status_code == 200          # организатор всё ещё может закрыть


async def test_open_games_limit_per_user(tmp_path, anyio_backend):
    async with run_app(tmp_path, max_open_games_per_user=2) as c:
        v = await _venue(c)
        org = await register(c, "organizer")
        assert (await org.post("/games", game_body(v["id"]))).status_code == 201
        assert (await org.post("/games", game_body(v["id"]))).status_code == 201
        assert (await org.post("/games", game_body(v["id"]))).status_code == 429


async def test_invite_friends(client):
    v = await _venue(client)
    org, friend, stranger = await register(client, "organizer"), await register(client, "friend1"), await register(client, "stranger")
    rid = (await org.post("/friend-requests", {"user_id": friend.id})).json()["request_id"]
    await friend.post(f"/friend-requests/{rid}/accept")
    gid = (await org.post("/games", game_body(v["id"]))).json()["id"]
    r = await org.post(f"/games/{gid}/invite", {"user_ids": [friend.id, stranger.id]})
    assert r.json() == {"sent": [friend.id], "skipped": [stranger.id]}
    msgs = (await friend.get(f"/messages/{org.id}")).json()["items"]
    assert "Вечерний баскетбол" in msgs[0]["body"]
    assert (await stranger.post(f"/games/{gid}/invite", {"user_ids": [friend.id]})).status_code == 403
