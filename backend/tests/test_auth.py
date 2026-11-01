"""Регистрация, вход, пароли, сессии."""
import pytest

from .conftest import API, PASSWORD, Actor, register, run_app, sql

pytestmark = pytest.mark.anyio


async def test_register_and_login(client):
    a = await register(client, "alex")
    assert a.user["login"] == "alex" and a.user["role"] == "user" and a.user["display_name"] == "alex"
    r = await client.post(f"{API}/auth/login", json={"login": "alex", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["token"]
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.json()["login"] == "alex"


async def test_login_is_case_sensitive_and_unique_per_case(client):
    await register(client, "Alex")
    other = await register(client, "alex")          # другой регистр — другой логин
    assert other.login == "alex"
    r = await client.post(f"{API}/auth/register", json={"login": "Alex", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "login_taken"
    bad = await client.post(f"{API}/auth/login", json={"login": "ALEX", "password": PASSWORD})
    assert bad.status_code == 401


async def test_password_rules(client):
    short = await client.post(f"{API}/auth/register", json={"login": "bob", "password": "1234567"})
    assert short.status_code == 422 and short.json()["error"]["code"] == "validation_error"
    # требований к составу пароля нет: только цифры, 8 знаков — допустимо
    ok = await client.post(f"{API}/auth/register", json={"login": "bob", "password": "12345678"})
    assert ok.status_code == 201


@pytest.mark.parametrize("login", ["ab", "a" * 33, "bad login", "x<y>z", "имя\u0000"])
async def test_invalid_logins_rejected(client, login):
    r = await client.post(f"{API}/auth/register", json={"login": login, "password": PASSWORD})
    assert r.status_code == 422


async def test_cyrillic_and_symbols_in_login(client):
    for login in ("Иван_1990", "user.name-1", "a@b+c"):
        r = await client.post(f"{API}/auth/register", json={"login": login, "password": PASSWORD})
        assert r.status_code == 201, login


async def test_password_is_stored_as_argon2_hash(client):
    a = await register(client, "hashme", "my secret pass")
    rows = await sql(client, "SELECT password_hash FROM users WHERE id = :id", id=a.id)
    stored = rows[0][0]
    assert stored.startswith("$argon2id$") and "my secret pass" not in stored
    # пароль не возвращается ни одним ответом
    assert "password" not in (await a.get("/auth/me")).text.lower().replace("must_change_password", "")


async def test_wrong_credentials_same_error(client):
    await register(client, "carol")
    wrong_pw = await client.post(f"{API}/auth/login", json={"login": "carol", "password": "wrong-password"})
    no_user = await client.post(f"{API}/auth/login", json={"login": "nobody", "password": "wrong-password"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


async def test_requires_token(client):
    assert (await client.get(f"{API}/venues")).status_code == 401
    r = await client.get(f"{API}/venues", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


async def test_logout_revokes_session(client):
    a = await register(client, "dave")
    assert (await a.post("/auth/logout")).status_code == 204
    assert (await a.get("/auth/me")).status_code == 401


async def test_login_rate_limit(tmp_path, anyio_backend):
    async with run_app(tmp_path, login_max_attempts=3) as c:
        await register(c, "erin")
        for _ in range(3):
            r = await c.post(f"{API}/auth/login", json={"login": "erin", "password": "bad-password"})
            assert r.status_code == 401
        r = await c.post(f"{API}/auth/login", json={"login": "erin", "password": PASSWORD})
        assert r.status_code == 429 and "Retry-After" in r.headers


async def test_register_rate_limit(tmp_path, anyio_backend):
    async with run_app(tmp_path, register_max_per_ip=2) as c:
        await register(c, "u1x")
        await register(c, "u2x")
        r = await c.post(f"{API}/auth/register", json={"login": "u3x", "password": PASSWORD})
        assert r.status_code == 429


async def test_cannot_self_assign_admin(client):
    r = await client.post(f"{API}/auth/register", json={"login": "sneaky", "password": PASSWORD, "role": "admin"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "user"
    a = Actor(client, r.json()["token"], r.json()["user"], PASSWORD)
    assert (await a.patch("/me", {"role": "admin", "display_name": "X"})).json()["role"] == "user"
    assert (await a.get("/admin/users")).status_code == 403


async def test_change_password_revokes_other_sessions(client):
    a = await register(client, "frank")
    other = await client.post(f"{API}/auth/login", json={"login": "frank", "password": PASSWORD})
    other_h = {"Authorization": f"Bearer {other.json()['token']}"}
    bad = await a.post("/auth/change-password", {"current_password": "nope-nope", "new_password": "new-password-1"})
    assert bad.status_code == 403
    ok = await a.post("/auth/change-password", {"current_password": PASSWORD, "new_password": "new-password-1"})
    assert ok.status_code == 200
    assert (await a.get("/auth/me")).status_code == 200                       # текущая сессия жива
    assert (await client.get(f"{API}/auth/me", headers=other_h)).status_code == 401   # другая — отозвана
    assert (await client.post(f"{API}/auth/login", json={"login": "frank", "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{API}/auth/login", json={"login": "frank", "password": "new-password-1"})).status_code == 200


async def test_change_login(client):
    a = await register(client, "gina")
    await register(client, "taken1")
    assert (await a.post("/auth/change-login", {"password": PASSWORD, "new_login": "taken1"})).status_code == 409
    assert (await a.post("/auth/change-login", {"password": "wrong-pass1", "new_login": "gina2"})).status_code == 403
    r = await a.post("/auth/change-login", {"password": PASSWORD, "new_login": "gina2"})
    assert r.status_code == 200 and r.json()["login"] == "gina2"
