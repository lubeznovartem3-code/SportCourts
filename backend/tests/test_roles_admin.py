"""Роли и права, заявки на модератора, сброс пароля, управление аккаунтами."""
import pytest

from .conftest import API, PASSWORD, admin_actor, make_role, register, sql

pytestmark = pytest.mark.anyio

ADMIN_ONLY = [
    ("GET", "/admin/users"), ("GET", "/admin/moderator-requests"), ("GET", "/admin/audit"),
    ("GET", "/admin/system"), ("GET", "/admin/sports"), ("GET", "/admin/reports"),
]


async def test_admin_endpoints_forbidden_for_user_and_moderator(client):
    user = await register(client, "plain")
    mod = await make_role(client, await register(client, "modder"), "moderator")
    for actor in (user, mod):
        for method, url in ADMIN_ONLY:
            r = await client.request(method, API + url, headers=actor.h)
            assert r.status_code == 403, (actor.login, url)
    assert (await user.get("/moderation/submissions")).status_code == 403


async def test_moderator_request_flow(client):
    admin = await admin_actor(client)
    u = await register(client, "wannabe")
    assert (await u.post("/moderator-requests", {"message": "Хочу помогать"})).status_code == 201
    assert (await u.post("/moderator-requests", {})).status_code == 409           # одна активная заявка
    pending = (await admin.get("/admin/moderator-requests")).json()["items"]
    assert len(pending) == 1 and pending[0]["user"]["login"] == "wannabe"
    assert (await admin.post(f"/admin/moderator-requests/{pending[0]['id']}/approve")).status_code == 200
    assert (await u.get("/auth/me")).json()["role"] == "moderator"
    notes = (await u.get("/notifications")).json()
    assert any(n["type"] == "moderator_request_decided" for n in notes["items"])
    assert (await admin.post(f"/admin/moderator-requests/{pending[0]['id']}/approve")).status_code == 409


async def test_reject_moderator_request_needs_reason(client):
    admin = await admin_actor(client)
    u = await register(client, "wannabe2")
    rid = (await u.post("/moderator-requests", {})).json()["id"]
    assert (await admin.post(f"/admin/moderator-requests/{rid}/reject", {"reason": " "})).status_code == 422
    assert (await admin.post(f"/admin/moderator-requests/{rid}/reject", {"reason": "Рано"})).status_code == 200
    assert (await u.get("/auth/me")).json()["role"] == "user"


async def test_set_role_rules(client):
    admin = await admin_actor(client)
    other_admin = await admin_actor(client, "admin2")
    u = await register(client, "target")
    assert (await admin.put(f"/admin/users/{u.id}/role", {"role": "moderator"})).status_code == 200
    assert (await admin.put(f"/admin/users/{u.id}/role", {"role": "admin"})).status_code == 422   # админов через API не создать
    assert (await admin.put(f"/admin/users/{admin.id}/role", {"role": "user"})).status_code == 403
    assert (await admin.put(f"/admin/users/{other_admin.id}/role", {"role": "user"})).status_code == 403
    assert (await u.get("/admin/users")).status_code == 403
    log = (await admin.get("/admin/audit")).json()["items"]
    assert any(e["action"] == "role_changed" for e in log)


async def test_reset_password_flow(client):
    admin = await admin_actor(client)
    u = await register(client, "forgetful", "old-password-1")
    r = await admin.post(f"/admin/users/{u.id}/reset-password")
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    assert len(temp) >= 10
    assert (await u.get("/auth/me")).status_code == 401                          # старые сессии отозваны
    assert (await client.post(f"{API}/auth/login", json={"login": "forgetful", "password": "old-password-1"})).status_code == 401
    login = await client.post(f"{API}/auth/login", json={"login": "forgetful", "password": temp})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {login.json()['token']}"}
    # пока пароль временный, остальное API закрыто
    blocked = await client.get(f"{API}/venues", headers=h)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 200
    ch = await client.post(f"{API}/auth/change-password", headers=h, json={"current_password": temp, "new_password": "brand-new-pass"})
    assert ch.status_code == 200 and ch.json()["must_change_password"] is False
    assert (await client.get(f"{API}/venues", headers=h)).status_code == 200
    # пароль не попал в журнал аудита
    log = await sql(client, "SELECT coalesce(details, '') FROM audit_log")
    assert all(temp not in row[0] for row in log)


async def test_cannot_reset_admin_password_via_api(client):
    admin = await admin_actor(client)
    other = await admin_actor(client, "admin2")
    assert (await admin.post(f"/admin/users/{other.id}/reset-password")).status_code == 403


async def test_disable_account(client):
    admin = await admin_actor(client)
    u = await register(client, "badguy")
    assert (await admin.put(f"/admin/users/{u.id}/active", {"is_active": False})).status_code == 200
    assert (await u.get("/auth/me")).status_code == 401
    r = await client.post(f"{API}/auth/login", json={"login": "badguy", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_disabled"
    assert (await admin.put(f"/admin/users/{u.id}/active", {"is_active": True})).status_code == 200
    assert (await client.post(f"{API}/auth/login", json={"login": "badguy", "password": PASSWORD})).status_code == 200


async def test_reports_visibility_for_moderators(client):
    admin = await admin_actor(client)
    mod = await make_role(client, await register(client, "modder"), "moderator")
    a, b = await register(client, "reporter"), await register(client, "culprit")
    assert (await a.post("/reports", {"target_user_id": b.id, "reason": "spam"})).status_code == 201
    assert (await mod.get("/admin/reports")).status_code == 403                      # по умолчанию — только админ
    assert (await admin.put(f"/admin/users/{mod.id}/review-reports", {"can_review_reports": True})).status_code == 200
    items = (await mod.get("/admin/reports")).json()["items"]
    assert len(items) == 1
    assert (await mod.post(f"/admin/reports/{items[0]['id']}/resolve", {"status": "resolved", "note": "ok"})).status_code == 200
    assert (await mod.post(f"/admin/reports/{items[0]['id']}/resolve", {"status": "dismissed"})).status_code == 409


async def test_report_validation(client):
    a, b = await register(client, "rep1"), await register(client, "rep2")
    assert (await a.post("/reports", {"target_user_id": a.id, "reason": "spam"})).status_code == 422
    assert (await a.post("/reports", {"reason": "spam"})).status_code == 422
    assert (await a.post("/reports", {"target_user_id": b.id, "target_venue_id": 1, "reason": "spam"})).status_code == 422
    assert (await a.post("/reports", {"target_user_id": 9999, "reason": "spam"})).status_code == 404
    assert (await a.post("/reports", {"target_user_id": b.id, "reason": "spam"})).status_code == 201
    assert (await a.post("/reports", {"target_user_id": b.id, "reason": "spam"})).status_code == 409


async def test_admin_sports_management(client):
    admin = await admin_actor(client)
    u = await register(client, "sporty")
    assert len((await u.get("/sports")).json()["items"]) == 3
    r = await admin.post("/admin/sports", {"name": "Теннис"})
    assert r.status_code == 201
    assert (await admin.post("/admin/sports", {"name": "Теннис"})).status_code == 409
    assert len((await u.get("/sports")).json()["items"]) == 4
    await admin.patch(f"/admin/sports/{r.json()['id']}", {"is_active": False})
    assert len((await u.get("/sports")).json()["items"]) == 3


async def test_system_status(client):
    admin = await admin_actor(client)
    r = await admin.get("/admin/system")
    assert r.status_code == 200 and r.json()["disk"]["free_gb"] > 0 and r.json()["counts"]["users"] == 1
