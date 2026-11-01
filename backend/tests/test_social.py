"""Друзья, личные сообщения, блокировки, уведомления, удаление аккаунта."""
import asyncio

import pytest

from .conftest import API, PASSWORD, admin_actor, create_venue, future, register, run_app, sql

pytestmark = pytest.mark.anyio


async def befriend(a, b):
    r = await a.post("/friend-requests", {"user_id": b.id})
    assert r.status_code == 201, r.text
    assert (await b.post(f"/friend-requests/{r.json()['request_id']}/accept")).status_code == 200


async def test_friend_request_accept_flow_and_notifications(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    r = await a.post("/friend-requests", {"user_id": b.id})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert (await a.post("/friend-requests", {"user_id": b.id})).status_code == 409        # повтор
    incoming = (await b.get("/friend-requests")).json()["items"]
    assert incoming[0]["user"]["login"] == "anna"
    assert (await a.get("/friend-requests", params={"direction": "outgoing"})).json()["items"][0]["user"]["login"] == "boris"
    note = (await b.get("/notifications")).json()
    assert note["unread_count"] == 1 and note["items"][0]["type"] == "friend_request"
    assert (await a.post(f"/friend-requests/{incoming[0]['id']}/accept")).status_code == 403   # принять может только получатель
    assert (await b.post(f"/friend-requests/{incoming[0]['id']}/accept")).status_code == 200
    assert (await b.post(f"/friend-requests/{incoming[0]['id']}/accept")).status_code == 409
    assert [f["login"] for f in (await a.get("/friends")).json()["items"]] == ["boris"]
    assert [f["login"] for f in (await b.get("/friends")).json()["items"]] == ["anna"]
    assert (await a.get("/notifications")).json()["items"][0]["type"] == "friend_accepted"
    assert (await a.post("/friend-requests", {"user_id": b.id})).status_code == 409        # уже друзья


async def test_mutual_requests_auto_accept(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    await a.post("/friend-requests", {"user_id": b.id})
    r = await b.post("/friend-requests", {"user_id": a.id})
    assert r.json()["status"] == "accepted"
    assert len((await a.get("/friends")).json()["items"]) == 1


async def test_decline_cancel_remove(client):
    a, b, c = await register(client, "anna"), await register(client, "boris"), await register(client, "clara")
    rid = (await a.post("/friend-requests", {"user_id": b.id})).json()["request_id"]
    assert (await b.post(f"/friend-requests/{rid}/decline")).status_code == 200
    assert (await b.get("/friends")).json()["items"] == []
    rid2 = (await a.post("/friend-requests", {"user_id": c.id})).json()["request_id"]      # после отказа можно снова
    assert (await c.delete(f"/friend-requests/{rid2}")).status_code == 403
    assert (await a.delete(f"/friend-requests/{rid2}")).status_code == 204
    await befriend(a, b)
    assert (await a.delete(f"/friends/{b.id}")).status_code == 204
    assert (await a.get("/friends")).json()["items"] == []
    assert (await a.delete(f"/friends/{b.id}")).status_code == 404
    assert (await a.post("/friend-requests", {"user_id": a.id})).status_code == 422
    assert (await a.post("/friend-requests", {"user_id": 9999})).status_code == 404


async def test_user_search_and_profile(client):
    a, b = await register(client, "anna"), await register(client, "Борис_Т", display_name="Борис Т")
    c = await register(client, "annabelle")
    assert (await a.get("/users/search", params={"q": "a"})).status_code == 422
    found = (await a.get("/users/search", params={"q": "ANN"})).json()["items"]
    assert [u["login"] for u in found] == ["annabelle"]                    # себя не показываем
    assert (await a.get("/users/search", params={"q": "борис"})).json()["items"][0]["relation"] == "none"
    assert (await a.get("/users/search", params={"q": "100%"})).json()["items"] == []
    await befriend(a, b)
    assert (await a.get("/users/search", params={"q": "борис"})).json()["items"][0]["relation"] == "friend"
    await a.post("/friend-requests", {"user_id": c.id})
    assert (await a.get("/users/search", params={"q": "annab"})).json()["items"][0]["relation"] == "request_sent"
    assert (await c.get("/users/search", params={"q": "anna"})).json()["items"][0]["relation"] in ("request_received", "none")
    assert "password_hash" not in (await a.get(f"/users/{b.id}")).text


async def test_online_status_only_for_friends(client):
    a, b, c = await register(client, "anna"), await register(client, "boris"), await register(client, "clara")
    await befriend(a, b)
    await b.get("/auth/me")                                                # любая активность обновляет last_seen
    assert (await a.get("/friends")).json()["items"][0]["online"] is True
    assert (await a.get(f"/users/{b.id}")).json()["online"] is True
    assert "online" not in (await c.get(f"/users/{b.id}")).json()         # посторонним статус не виден
    await sql(client, "UPDATE users SET last_seen_at = now() - interval '10 minutes' WHERE id = :i", i=b.id)
    assert (await a.get("/friends")).json()["items"][0]["online"] is False
    assert (await a.get(f"/users/{b.id}")).json()["online"] is False


async def test_friend_activity_text(client):
    admin = await admin_actor(client)
    v = await create_venue(client, admin)
    a, b = await register(client, "anna"), await register(client, "boris")
    await befriend(a, b)
    assert (await a.get("/friends")).json()["items"][0]["activity"] is None
    await b.post(f"/venues/{v['id']}/presence/toggle")
    assert "Хамовники" in (await a.get("/friends")).json()["items"][0]["activity"]
    await b.post("/games", {"venue_id": v["id"], "title": "Баскетбол 5х5", "starts_at": future(2), "max_players": 6})
    assert "Баскетбол 5х5" in (await a.get("/friends")).json()["items"][0]["activity"]


# ----------------------------------------------------------------------------- сообщения
async def test_messages_only_between_friends(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    r = await a.post(f"/messages/{b.id}", {"body": "Привет"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_friends"
    await befriend(a, b)
    assert (await a.post(f"/messages/{b.id}", {"body": "Привет"})).status_code == 201
    assert (await a.post(f"/messages/{b.id}", {"body": "   "})).status_code == 422
    assert (await a.post(f"/messages/{b.id}", {"body": "x" * 2001})).status_code == 422
    assert (await a.post(f"/messages/{a.id}", {"body": "себе"})).status_code == 422
    assert (await a.post("/messages/9999", {"body": "никому"})).status_code == 404


async def test_message_history_and_pagination(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    await befriend(a, b)
    for i in range(25):
        await (a if i % 2 == 0 else b).post(f"/messages/{(b if i % 2 == 0 else a).id}", {"body": f"сообщение {i}"})
    page1 = (await a.get(f"/messages/{b.id}", params={"limit": 10})).json()
    assert [m["body"] for m in page1["items"]] == [f"сообщение {i}" for i in range(15, 25)]   # от старых к новым
    assert page1["has_more"] is True
    page2 = (await a.get(f"/messages/{b.id}", params={"limit": 10, "before_id": page1["items"][0]["id"]})).json()
    assert [m["body"] for m in page2["items"]] == [f"сообщение {i}" for i in range(5, 15)] and page2["has_more"] is True
    page3 = (await a.get(f"/messages/{b.id}", params={"limit": 10, "before_id": page2["items"][0]["id"]})).json()
    assert len(page3["items"]) == 5 and page3["has_more"] is False
    last_id = page1["items"][-1]["id"]
    await b.post(f"/messages/{a.id}", {"body": "новое"})
    new = (await a.get(f"/messages/{b.id}", params={"after_id": last_id})).json()["items"]
    assert [m["body"] for m in new] == ["новое"] and new[0]["mine"] is False
    assert all(m["mine"] == (m["sender_id"] == a.id) for m in page1["items"])
    c = await register(client, "clara")
    assert (await c.get(f"/messages/{a.id}")).json()["items"] == []        # чужую переписку увидеть нельзя


async def test_conversations_unread_and_read(client):
    a, b, c = await register(client, "anna"), await register(client, "boris"), await register(client, "clara")
    await befriend(a, b)
    await befriend(a, c)
    await b.post(f"/messages/{a.id}", {"body": "раз"})
    await b.post(f"/messages/{a.id}", {"body": "два"})
    await c.post(f"/messages/{a.id}", {"body": "привет от клары"})
    convs = (await a.get("/conversations")).json()["items"]
    assert [x["user"]["login"] for x in convs] == ["clara", "boris"]        # свежие диалоги выше
    assert {x["user"]["login"]: x["unread"] for x in convs} == {"clara": 1, "boris": 2}
    assert convs[1]["last_message"]["body"] == "два"
    assert (await a.get("/notifications/unread-count")).json()["unread_messages"] == 3
    assert (await a.post(f"/messages/{b.id}/read")).status_code == 204
    assert {x["user"]["login"]: x["unread"] for x in (await a.get("/conversations")).json()["items"]}["boris"] == 0
    assert (await a.get("/friends")).json()["items"][0]["unread_messages"] in (0, 1)


async def test_message_rate_limit(tmp_path, anyio_backend):
    async with run_app(tmp_path, message_max_per_minute=3) as c:
        a, b = await register(c, "anna"), await register(c, "boris")
        await befriend(a, b)
        codes = [(await a.post(f"/messages/{b.id}", {"body": f"m{i}"})).status_code for i in range(5)]
        assert codes == [201, 201, 201, 429, 429]


# ----------------------------------------------------------------------------- блокировки
async def test_block_is_two_way_and_breaks_friendship(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    await befriend(a, b)
    await b.post(f"/messages/{a.id}", {"body": "до блокировки"})
    assert (await a.post(f"/blocks/{b.id}")).status_code == 204
    assert (await a.get("/friends")).json()["items"] == []                  # дружба разорвана
    assert (await b.get("/friends")).json()["items"] == []
    for actor, other in ((a, b), (b, a)):                                    # блокировка действует в обе стороны
        assert (await actor.post(f"/messages/{other.id}", {"body": "эй"})).status_code == 403
        assert (await actor.get(f"/messages/{other.id}")).status_code == 403
        assert (await actor.post("/friend-requests", {"user_id": other.id})).status_code == 403
        assert (await actor.get("/users/search", params={"q": other.login})).json()["items"] == []
    assert (await b.get("/conversations")).json()["items"] == []
    assert (await b.get(f"/users/{a.id}")).status_code == 404               # заблокировавший «не существует»
    assert (await a.get(f"/users/{b.id}")).json()["blocked_by_me"] is True
    assert [x["user"]["login"] for x in (await a.get("/blocks")).json()["items"]] == ["boris"]
    assert (await a.delete(f"/blocks/{b.id}")).status_code == 204
    assert (await b.post("/friend-requests", {"user_id": a.id})).status_code == 201     # после разблокировки снова можно
    assert (await a.post(f"/blocks/{a.id}")).status_code == 422
    assert (await a.post("/blocks/9999")).status_code == 404


async def test_block_cancels_pending_requests_and_game_join(client):
    admin = await admin_actor(client)
    v = await create_venue(client, admin)
    a, b = await register(client, "anna"), await register(client, "boris")
    await a.post("/friend-requests", {"user_id": b.id})
    gid = (await a.post("/games", {"venue_id": v["id"], "title": "Игра", "starts_at": future(2), "max_players": 4})).json()["id"]
    await a.post(f"/blocks/{b.id}")
    assert (await b.get("/friend-requests")).json()["items"] == []
    r = await b.post(f"/games/{gid}/join")
    assert r.status_code == 403 and r.json()["error"]["code"] == "blocked"
    assert gid not in [g["id"] for g in (await b.get("/games")).json()["items"]]


# ----------------------------------------------------------------------------- уведомления
async def test_notification_read_flow(client):
    a, b = await register(client, "anna"), await register(client, "boris")
    await a.post("/friend-requests", {"user_id": b.id})
    n = (await b.get("/notifications")).json()["items"][0]
    assert (await a.post(f"/notifications/{n['id']}/read")).status_code == 204       # чужое не затрагивает
    assert (await b.get("/notifications/unread-count")).json()["unread_count"] == 1
    assert (await b.post(f"/notifications/{n['id']}/read")).status_code == 204
    assert (await b.get("/notifications/unread-count")).json()["unread_count"] == 0
    assert (await b.post("/notifications/read-all")).status_code == 204


# ----------------------------------------------------------------------------- удаление аккаунта
async def test_delete_account_removes_personal_data(client, tmp_path):
    admin = await admin_actor(client)
    v = await create_venue(client, admin)
    a, b = await register(client, "anna", display_name="Анна"), await register(client, "boris")
    await befriend(a, b)
    await a.post(f"/messages/{b.id}", {"body": "секретная переписка"})
    await a.patch("/me", {"favorite_sport_ids": [1, 2]})
    await a.post(f"/venues/{v['id']}/presence/toggle")
    await a.post(f"/venues/{v['id']}/player-reports", {"player_count": 5})
    gid = (await a.post("/games", {"venue_id": v["id"], "title": "Моя игра", "starts_at": future(2), "max_players": 4})).json()["id"]
    await a.post("/venue-submissions", {"name": "Заявка", "address": "адрес", "latitude": 50, "longitude": 40,
                                         "venue_type": "indoor", "sport_ids": [1]})
    from .conftest import png_bytes
    await a.client.put(f"{API}/me/avatar", headers=a.h, files={"file": ("a.png", png_bytes(), "image/png")})
    assert list((tmp_path / "uploads" / "avatars").glob("*.jpg"))

    assert (await a.delete("/me", {"password": "wrong-password"})).status_code == 403
    assert (await a.delete("/me", {"password": PASSWORD})).status_code == 204
    assert (await a.get("/auth/me")).status_code == 401
    assert (await client.post(f"{API}/auth/login", json={"login": "anna", "password": PASSWORD})).status_code == 401
    assert not list((tmp_path / "uploads" / "avatars").glob("*.jpg"))              # аватар удалён с диска
    assert (await sql(client, "SELECT count(*) FROM messages"))[0][0] == 0
    assert (await sql(client, "SELECT count(*) FROM friendships"))[0][0] == 0
    assert (await sql(client, "SELECT count(*) FROM user_favorite_sports"))[0][0] == 0
    assert (await sql(client, "SELECT count(*) FROM venue_submissions"))[0][0] == 0   # ожидающие заявки удалены
    row = (await sql(client, "SELECT login, display_name, password_hash, avatar_path, is_active FROM users WHERE id = :i", i=a.id))[0]
    assert row[0] == f"deleted:{a.id}" and row[1] == "Удалённый пользователь" and row[2] == "!" and row[3] is None and row[4] is False
    # игры и отчёты остаются целостными, но без личных данных
    assert (await b.get(f"/games/{gid}")).json()["status"] == "cancelled"
    assert (await b.get(f"/venues/{v['id']}")).json()["checked_in_count"] == 0
    assert (await b.get(f"/venues/{v['id']}/player-reports")).json()["items"][0]["reporter"]["display_name"] == "Удалённый пользователь"
    assert (await b.get("/friends")).json()["items"] == []
    assert (await b.get(f"/users/{a.id}")).status_code == 404
    # логин освободился для регистрации
    assert (await client.post(f"{API}/auth/register", json={"login": "anna", "password": PASSWORD})).status_code == 201


async def test_last_admin_cannot_delete_account(client):
    admin = await admin_actor(client)
    r = await admin.delete("/me", {"password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    other = await admin_actor(client, "admin2")
    assert (await other.delete("/me", {"password": PASSWORD})).status_code == 204


async def test_profile_update_and_avatar(client, tmp_path):
    from .conftest import png_bytes
    a = await register(client, "anna")
    r = await a.patch("/me", {"display_name": "  Анна   Петрова ", "favorite_sport_ids": [1, 2, 2]})
    assert r.json()["display_name"] == "Анна Петрова" and [s["name"] for s in r.json()["favorite_sports"]] == ["Футбол", "Баскетбол"]
    assert (await a.patch("/me", {"favorite_sport_ids": [99]})).status_code == 422
    assert (await a.patch("/me", {"display_name": "   "})).status_code == 422
    up = await a.client.put(f"{API}/me/avatar", headers=a.h, files={"file": ("a.png", png_bytes((2000, 2000)), "image/png")})
    url = up.json()["avatar_url"]
    assert url.startswith("/media/avatars/") and (await client.get(url)).status_code == 200
    from PIL import Image
    import io
    assert max(Image.open(io.BytesIO((await client.get(url)).content)).size) <= 512
    up2 = await a.client.put(f"{API}/me/avatar", headers=a.h, files={"file": ("a.png", png_bytes(), "image/png")})
    assert len(list((tmp_path / "uploads" / "avatars").glob("*.jpg"))) == 1      # старый файл удалён
    bad = await a.client.put(f"{API}/me/avatar", headers=a.h, files={"file": ("a.exe", b"MZ\x90\x00\x03", "application/octet-stream")})
    assert bad.status_code == 422
    assert (await a.delete("/me/avatar")).json()["avatar_url"] is None
    assert not list((tmp_path / "uploads" / "avatars").glob("*.jpg"))
