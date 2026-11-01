"""Первый администратор и служебные команды."""
import os

import pytest
from sqlalchemy import text

from app import cli
from app.config import load_settings

from .conftest import API, TEST_DB_URL, PASSWORD, register, run_app, sql

pytestmark = pytest.mark.anyio


def settings_for(tmp_path, **env):
    base = {"DATABASE_URL": TEST_DB_URL, "SECRET_KEY": "s" * 40, "UPLOADS_DIR": str(tmp_path / "up"),
            "LOGS_DIR": str(tmp_path / "logs"), "DATA_DIR": str(tmp_path / "data")}
    return load_settings(environ={**base, **env}, env_file=os.devnull)


async def test_create_admin_is_idempotent(client, tmp_path):
    s = settings_for(tmp_path, ADMIN_LOGIN="boss", ADMIN_PASSWORD="initial-pass-1")
    status, msg = await cli.create_admin(s, interactive=False)
    assert status == "created" and "сменить" in msg
    row = (await sql(client, "SELECT role, must_change_password, password_hash FROM users WHERE login = 'boss'"))[0]
    assert row[0] == "admin" and row[1] is True and row[2].startswith("$argon2id$")
    first_hash = row[2]
    # повторный запуск (в том числе с другим паролем) ничего не меняет и не дублирует
    s2 = settings_for(tmp_path, ADMIN_LOGIN="boss", ADMIN_PASSWORD="another-pass-2")
    status, msg = await cli.create_admin(s2, interactive=False)
    assert status == "exists" and "не изменено" in msg
    assert (await sql(client, "SELECT count(*) FROM users WHERE login = 'boss'"))[0][0] == 1
    assert (await sql(client, "SELECT password_hash FROM users WHERE login = 'boss'"))[0][0] == first_hash


async def test_admin_from_env_must_change_password_at_first_login(client, tmp_path):
    await cli.create_admin(settings_for(tmp_path, ADMIN_LOGIN="boss", ADMIN_PASSWORD="initial-pass-1"), interactive=False)
    r = await client.post(f"{API}/auth/login", json={"login": "boss", "password": "initial-pass-1"})
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True and r.json()["user"]["role"] == "admin"
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert (await client.get(f"{API}/admin/users", headers=h)).status_code == 403          # пока пароль временный
    ch = await client.post(f"{API}/auth/change-password", headers=h,
                           json={"current_password": "initial-pass-1", "new_password": "my-own-password"})
    assert ch.status_code == 200
    assert (await client.get(f"{API}/admin/users", headers=h)).status_code == 200


async def test_create_admin_refuses_existing_regular_user(client, tmp_path):
    await register(client, "boss")
    status, msg = await cli.create_admin(settings_for(tmp_path, ADMIN_LOGIN="boss", ADMIN_PASSWORD="initial-pass-1"), interactive=False)
    assert status == "exists" and (await sql(client, "SELECT role FROM users WHERE login = 'boss'"))[0][0] == "user"


@pytest.mark.parametrize("env,fragment", [
    ({}, "ADMIN_LOGIN"), ({"ADMIN_LOGIN": "boss"}, "ADMIN_PASSWORD"),
    ({"ADMIN_LOGIN": "boss", "ADMIN_PASSWORD": "short"}, "пароль"), ({"ADMIN_LOGIN": "b d", "ADMIN_PASSWORD": "initial-pass-1"}, "ADMIN_LOGIN"),
])
async def test_create_admin_errors(client, tmp_path, env, fragment):
    status, msg = await cli.create_admin(settings_for(tmp_path, **env), interactive=False)
    assert status == "error" and fragment.lower() in msg.lower()
    assert (await sql(client, "SELECT count(*) FROM users"))[0][0] == 0


async def test_cli_reset_password(client, tmp_path):
    u = await register(client, "forgetful")
    s = settings_for(tmp_path)
    ok, msg = await cli.reset_password(s, "forgetful", None)
    assert ok and "Временный пароль" in msg
    temp = msg.split(": ")[1].split("\n")[0]
    assert (await u.get("/auth/me")).status_code == 401
    r = await client.post(f"{API}/auth/login", json={"login": "forgetful", "password": temp})
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    assert (await cli.reset_password(s, "ghost", None))[0] is False
    ok, _ = await cli.reset_password(s, "forgetful", "chosen-password-9")
    assert ok and (await client.post(f"{API}/auth/login", json={"login": "forgetful", "password": "chosen-password-9"})).status_code == 200


async def test_check_command_reports_state(client, tmp_path, capsys):
    s = settings_for(tmp_path)
    assert await cli.run_check(s) == 1                       # администратора ещё нет
    out = capsys.readouterr().out
    assert "Подключение к PostgreSQL" in out and "[ OK ] Подключение" in out and "create-admin" in out
    await cli.create_admin(settings_for(tmp_path, ADMIN_LOGIN="boss", ADMIN_PASSWORD="initial-pass-1"), interactive=False)
    assert await cli.run_check(s) == 0
    bad = settings_for(tmp_path, DATABASE_URL=TEST_DB_URL.replace(":5432/", ":1/"))
    assert await cli.run_check(bad) == 1
    assert "[FAIL] Подключение к PostgreSQL" in capsys.readouterr().out


def test_stop_server_without_pid_file(tmp_path):
    ok, msg = cli.stop_server(settings_for(tmp_path), timeout=1)
    assert ok and "не запущен" in msg


def test_stop_server_cleans_stale_pid_file(tmp_path):
    s = settings_for(tmp_path)
    s.data_path.mkdir(parents=True)
    (s.data_path / "server.pid").write_text("999999")           # такого процесса нет
    ok, msg = cli.stop_server(s, timeout=1)
    assert ok and "устаревший" in msg and not (s.data_path / "server.pid").exists()


def test_stop_server_asks_running_process_to_stop(tmp_path):
    """Настоящий дочерний процесс видит stop.flag, завершается и stop_server сообщает об успехе."""
    import subprocess
    import sys
    s = settings_for(tmp_path)
    s.data_path.mkdir(parents=True)
    flag = s.data_path / "stop.flag"
    code = ("import sys, time, pathlib\\nf = pathlib.Path(sys.argv[1])\\n"
            "for _ in range(100):\\n    time.sleep(0.1)\\n    if f.exists():\\n        break\\n")
    proc = subprocess.Popen([sys.executable, "-c", code.replace("\\n", "\n"), str(flag)])
    import threading
    threading.Thread(target=proc.wait, daemon=True).start()      # забирает код завершения, чтобы процесс не остался «зомби»
    try:
        (s.data_path / "server.pid").write_text(str(proc.pid))
        ok, msg = cli.stop_server(s, timeout=10)
        assert ok and "остановлен" in msg
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_server_reports_when_process_ignores_request(tmp_path):
    import subprocess
    import sys
    s = settings_for(tmp_path)
    s.data_path.mkdir(parents=True)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (s.data_path / "server.pid").write_text(str(proc.pid))
        ok, msg = cli.stop_server(s, timeout=1)
        assert not ok and "taskkill" in msg
    finally:
        proc.kill()
