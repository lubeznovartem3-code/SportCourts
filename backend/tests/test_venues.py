"""Площадки, заявки, предложения изменений, модерация, фото."""
import pytest

from .conftest import (API, admin_actor, create_venue, make_role, png_bytes, register, sql, venue_payload)

pytestmark = pytest.mark.anyio


async def test_empty_catalog(client):
    u = await register(client, "viewer")
    r = await u.get("/venues")
    assert r.status_code == 200 and r.json() == {"items": [], "total": 0, "limit": 200, "offset": 0}


async def test_only_admin_creates_venues_directly(client):
    u = await register(client, "plain")
    assert (await u.post("/admin/venues", venue_payload())).status_code == 403


async def test_admin_creates_and_lists_venue(client):
    admin = await admin_actor(client)
    v = await create_venue(client, admin)
    assert v["name"] == "Хамовники Арена" and v["sports"][0]["name"] == "Баскетбол"
    u = await register(client, "viewer")
    listing = (await u.get("/venues")).json()
    assert listing["total"] == 1 and listing["items"][0]["checked_in_count"] == 0
    assert listing["items"][0]["latest_report"] is None
    detail = (await u.get(f"/venues/{v['id']}")).json()
    assert detail["description"] == "Открытая площадка" and detail["my_presence"]["active"] is False
    assert (await u.get("/venues/9999")).status_code == 404


async def test_search_filters_sort_and_distance(client):
    admin = await admin_actor(client)
    a = await create_venue(client, admin, name="Лужники Футбол", sport_ids=[1], venue_type="outdoor",
                           latitude=55.7158, longitude=37.5538, address="ул. Лужники, 24")
    b = await create_venue(client, admin, name="Арена Волей", sport_ids=[3], venue_type="indoor",
                           latitude=55.80, longitude=37.60, address="Проспект Мира, 1")
    c = await create_venue(client, admin, name="Дальняя", sport_ids=[1, 2], venue_type="outdoor",
                           latitude=59.93, longitude=30.31, address="Санкт-Петербург")
    u = await register(client, "viewer")
    names = lambda r: [i["name"] for i in r.json()["items"]]
    assert names(await u.get("/venues", params={"q": "ЛУЖНИКИ"})) == ["Лужники Футбол"]   # регистр и адрес
    assert names(await u.get("/venues", params={"q": "100%_"})) == []                      # спецсимволы LIKE экранируются
    assert names(await u.get("/venues", params={"sport_id": 3})) == ["Арена Волей"]
    assert sorted(names(await u.get("/venues", params={"sport_id": 1}))) == ["Дальняя", "Лужники Футбол"]
    assert names(await u.get("/venues", params={"venue_type": "indoor"})) == ["Арена Волей"]
    r = await u.get("/venues", params={"lat": 55.7, "lon": 37.55, "sort": "distance"})
    assert names(r) == ["Лужники Футбол", "Арена Волей", "Дальняя"]
    assert 0 < r.json()["items"][0]["distance_km"] < 3 and r.json()["items"][2]["distance_km"] > 600
    near = await u.get("/venues", params={"lat": 55.7, "lon": 37.55, "radius_km": 30})
    assert sorted(names(near)) == ["Арена Волей", "Лужники Футбол"]
    assert (await u.get("/venues", params={"lat": 55.7})).status_code == 422               # одна координата
    # без координат сортировка по расстоянию мягко превращается в сортировку по названию
    assert (await u.get("/venues", params={"sort": "distance"})).status_code == 200
    # фильтр по числу игроков
    await u.post(f"/venues/{a['id']}/presence/toggle")
    assert names(await u.get("/venues", params={"min_players": 1})) == ["Лужники Футбол"]
    assert (await u.get("/venues", params={"min_players": 1})).json()["items"][0]["players_estimate"] == 1
    page = (await u.get("/venues", params={"limit": 1, "offset": 1})).json()
    assert page["total"] == 3 and len(page["items"]) == 1


async def test_archived_venue_hidden(client):
    admin = await admin_actor(client)
    v = await create_venue(client, admin)
    u = await register(client, "viewer")
    assert (await admin.put(f"/admin/venues/{v['id']}/archive", {"archived": True})).status_code == 200
    assert (await u.get("/venues")).json()["total"] == 0
    assert (await u.get(f"/venues/{v['id']}")).status_code == 404
    assert (await u.post(f"/venues/{v['id']}/presence/toggle")).status_code == 404


async def test_validation_errors_are_russian_and_structured(client):
    admin = await admin_actor(client)
    r = await admin.post("/admin/venues", venue_payload(latitude=123))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["details"][0]["field"] == "latitude"
    assert (await admin.post("/admin/venues", venue_payload(sport_ids=[]))).status_code == 422
    assert (await admin.post("/admin/venues", venue_payload(sport_ids=[99]))).status_code == 422
    assert (await admin.post("/admin/venues", venue_payload(name="   "))).status_code == 422


async def test_submission_approval_flow(client):
    admin = await admin_actor(client)
    mod = await make_role(client, await register(client, "modder"), "moderator")
    u = await register(client, "proposer")
    r = await u.post("/venue-submissions", venue_payload("Новая площадка", latitude=55.9, longitude=37.9))
    assert r.status_code == 201 and r.json()["status"] == "pending"
    sid = r.json()["id"]
    assert (await u.get("/venues")).json()["total"] == 0                       # не публична до одобрения
    assert (await mod.get("/moderation/submissions")).json()["items"][0]["submitter"]["login"] == "proposer"
    assert (await u.get("/moderation/submissions")).status_code == 403
    ok = await mod.post(f"/moderation/submissions/{sid}/approve")
    assert ok.status_code == 200
    listing = (await u.get("/venues")).json()
    assert listing["total"] == 1 and listing["items"][0]["name"] == "Новая площадка"
    assert (await mod.post(f"/moderation/submissions/{sid}/approve")).status_code == 409
    mine = (await u.get("/venue-submissions/mine")).json()["items"][0]
    assert mine["status"] == "approved" and mine["venue_id"] == listing["items"][0]["id"]
    notes = (await u.get("/notifications")).json()["items"]
    assert notes[0]["type"] == "venue_submission_decided"
    hist = (await mod.get("/moderation/decisions")).json()["items"]
    assert hist[0]["decision"] == "approved" and hist[0]["moderator"]["login"] == "modder"


async def test_submission_rejection_requires_reason_and_is_kept_in_history(client):
    mod = await make_role(client, await register(client, "modder"), "moderator")
    u = await register(client, "proposer")
    sid = (await u.post("/venue-submissions", venue_payload())).json()["id"]
    assert (await mod.post(f"/moderation/submissions/{sid}/reject", {"reason": ""})).status_code == 422
    assert (await mod.post(f"/moderation/submissions/{sid}/reject", {"reason": "Такая площадка уже есть"})).status_code == 200
    mine = (await u.get("/venue-submissions/mine")).json()["items"][0]
    assert mine["status"] == "rejected" and mine["decision_reason"] == "Такая площадка уже есть"
    assert [x["name"] for x in mine["sports"]] == ["Баскетбол"]          # регрессия: виды спорта заявки не терялись
    queue_item = (await mod.get("/moderation/submissions", params={"status": "rejected"})).json()["items"][0]
    assert [x["name"] for x in queue_item["sports"]] == ["Баскетбол"]
    assert (await u.get("/venues")).json()["total"] == 0
    assert "Такая площадка" in (await u.get("/notifications")).json()["items"][0]["body"]
    assert (await mod.get("/moderation/decisions")).json()["items"][0]["decision"] == "rejected"


async def test_moderator_cannot_decide_own_submission(client):
    mod = await make_role(client, await register(client, "modder"), "moderator")
    sid = (await mod.post("/venue-submissions", venue_payload())).json()["id"]
    r = await mod.post(f"/moderation/submissions/{sid}/approve")
    assert r.status_code == 403 and r.json()["error"]["code"] == "own_submission"


async def test_duplicate_warning_and_force(client):
    admin = await admin_actor(client)
    await create_venue(client, admin)
    u = await register(client, "proposer")
    same_spot = venue_payload("Другое название", latitude=55.7159, longitude=37.5539)
    r = await u.post("/venue-submissions", same_spot)
    assert r.status_code == 409 and r.json()["error"]["code"] == "possible_duplicates"
    dup = r.json()["error"]["details"]["duplicates"][0]
    assert dup["kind"] == "venue" and dup["distance_m"] < 100
    same_name = await u.post("/venue-submissions", venue_payload("хамовники арена", latitude=56.5, longitude=38.5))
    assert same_name.status_code == 409                                          # то же название в другом месте
    assert (await u.post("/venues/check-duplicates", same_spot)).json()["duplicates"]
    forced = await u.post("/venue-submissions", {**same_spot, "force": True})
    assert forced.status_code == 201                                             # ничего не склеивается автоматически
    assert (await u.get("/venues")).json()["total"] == 1
    far = await u.post("/venue-submissions", venue_payload("Совсем другая", latitude=50.0, longitude=40.0))
    assert far.status_code == 201


async def test_pending_submission_limit(tmp_path, anyio_backend):
    from .conftest import run_app
    async with run_app(tmp_path, max_pending_submissions_per_user=2) as c:
        u = await register(c, "spammer")
        for i in range(2):
            assert (await u.post("/venue-submissions", venue_payload(f"П{i}", latitude=50 + i, longitude=40 + i))).status_code == 201
        assert (await u.post("/venue-submissions", venue_payload("П3", latitude=60, longitude=45))).status_code == 429


async def test_change_proposal_flow(client):
    admin = await admin_actor(client)
    mod = await make_role(client, await register(client, "modder"), "moderator")
    v = await create_venue(client, admin)
    u = await register(client, "editor")
    body = venue_payload("Хамовники Арена (обновлено)", sport_ids=[1, 2], work_hours="09:00 - 22:00", force=True)
    r = await u.post(f"/venues/{v['id']}/proposals", body)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert (await u.get(f"/venues/{v['id']}")).json()["name"] == "Хамовники Арена"        # пока без изменений
    item = (await mod.get("/moderation/proposals")).json()["items"][0]
    assert item["name"].endswith("(обновлено)") and item["current"]["name"] == "Хамовники Арена"
    assert (await mod.post(f"/moderation/proposals/{pid}/approve")).status_code == 200
    d = (await u.get(f"/venues/{v['id']}")).json()
    assert d["name"].endswith("(обновлено)") and d["work_hours"] == "09:00 - 22:00"
    assert sorted(s["name"] for s in d["sports"]) == ["Баскетбол", "Футбол"]
    # второе предложение отклоняется
    pid2 = (await u.post(f"/venues/{v['id']}/proposals", {**body, "name": "Хулиганство"})).json()["id"]
    assert (await mod.post(f"/moderation/proposals/{pid2}/reject", {"reason": "Некорректное название"})).status_code == 200
    assert "Хулиганство" not in (await u.get(f"/venues/{v['id']}")).text
    assert (await u.get("/venue-change-proposals/mine")).json()["items"][0]["status"] == "rejected"
    assert (await u.post("/venues/9999/proposals", body)).status_code == 404


async def test_photo_upload_flow(client, tmp_path):
    admin = await admin_actor(client)
    u = await register(client, "photographer")
    bad = await u.client.post(f"{API}/uploads/venue-photo", headers=u.h, files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_image"
    up = await u.client.post(f"{API}/uploads/venue-photo", headers=u.h, files={"file": ("p.png", png_bytes((3000, 2000)), "image/png")})
    assert up.status_code == 201
    token = up.json()["token"]
    # чужой токен не работает
    other = await register(client, "thief")
    assert (await other.post("/venue-submissions", venue_payload(photo_token=token))).status_code == 422
    sid = (await u.post("/venue-submissions", venue_payload(photo_token=token))).json()["id"]
    assert (await u.post("/venue-submissions", venue_payload("Другая", latitude=40, longitude=40, photo_token=token))).status_code == 422  # токен одноразовый
    mod = await make_role(client, await register(client, "modder"), "moderator")
    await mod.post(f"/moderation/submissions/{sid}/approve")
    url = (await u.get("/venues")).json()["items"][0]["photo_url"]
    assert url.startswith("/media/venues/")
    media = await client.get(url)                        # фото доступно без заголовков (для загрузчика изображений)
    assert media.status_code == 200 and media.headers["content-type"] == "image/jpeg"
    assert "immutable" in media.headers["cache-control"]
    from PIL import Image
    import io
    assert max(Image.open(io.BytesIO(media.content)).size) <= 1600
    assert (await client.get("/media/venues/..%2f..%2fetc%2fpasswd")).status_code == 404
    assert (await client.get("/media/venues/" + "0" * 32 + ".jpg")).status_code == 404


async def test_rejected_submission_deletes_photo(client, tmp_path):
    u = await register(client, "photographer")
    token = (await u.client.post(f"{API}/uploads/venue-photo", headers=u.h,
                                 files={"file": ("p.png", png_bytes(), "image/png")})).json()["token"]
    sid = (await u.post("/venue-submissions", venue_payload(photo_token=token))).json()["id"]
    files = list((tmp_path / "uploads" / "venues").glob("*.jpg"))
    assert len(files) == 1
    mod = await make_role(client, await register(client, "modder"), "moderator")
    await mod.post(f"/moderation/submissions/{sid}/reject", {"reason": "Плохое фото"})
    assert not list((tmp_path / "uploads" / "venues").glob("*.jpg"))


async def test_upload_size_limit(tmp_path, anyio_backend):
    from .conftest import run_app
    async with run_app(tmp_path, max_upload_mb=1, max_request_mb=2) as c:
        u = await register(c, "big")
        huge = b"\x89PNG" + b"0" * (3 * 1024 * 1024)
        r = await c.post(f"{API}/uploads/venue-photo", headers=u.h, files={"file": ("p.png", huge, "image/png")})
        assert r.status_code == 413
