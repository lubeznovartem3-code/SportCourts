"""Резервное копирование и восстановление (нужны pg_dump/pg_restore/psql; если их нет — тесты пропускаются)."""
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import backup
from app.config import load_settings
from .conftest import TEST_DB_URL


def make_settings(tmp_path: Path, **extra):
    env = {"DATABASE_URL": TEST_DB_URL, "SECRET_KEY": "test-secret-key-" + "x" * 32,
           "UPLOADS_DIR": str(tmp_path / "uploads"), "LOGS_DIR": str(tmp_path / "logs"), "DATA_DIR": str(tmp_path / "data"),
           "BACKUP_DIR": str(tmp_path / "backups"), "BACKUP_MIN_KEEP": "2", "BACKUP_RETENTION_DAYS": "14",
           **{k.upper(): str(v) for k, v in extra.items()}}
    return load_settings(environ=env, env_file=os.devnull)


@pytest.fixture
def settings(tmp_path):
    s = make_settings(tmp_path)
    try:
        backup.find_pg_tool(s, "pg_dump"), backup.find_pg_tool(s, "pg_restore"), backup.find_pg_tool(s, "psql")
    except backup.BackupError:
        pytest.skip("PostgreSQL client tools не найдены")
    (tmp_path / "uploads" / "venues").mkdir(parents=True)
    (tmp_path / "uploads" / "staging").mkdir()
    (tmp_path / "data").mkdir()
    return s


def psql(settings, sql: str) -> str:
    env, conn = backup.pg_env(settings)
    return backup.run_tool([backup.find_pg_tool(settings, "psql"), *conn, "--dbname", backup.db_name(settings), "-At", "-c", sql],
                           env, "psql").strip()


def logins(settings) -> str:
    return psql(settings, "SELECT coalesce(string_agg(login, ',' ORDER BY login), '') FROM users")


@pytest.fixture
def seeded(settings, tmp_path):
    psql(settings, "TRUNCATE users RESTART IDENTITY CASCADE")
    psql(settings, "INSERT INTO users (login, password_hash, display_name) VALUES ('before1', 'x', 'Before')")
    (tmp_path / "uploads" / "venues" / "a.jpg").write_bytes(b"photo-a")
    (tmp_path / "uploads" / "staging" / "tmp.jpg").write_bytes(b"draft")
    return settings


def test_backup_creates_verified_copy_without_drafts(seeded, tmp_path):
    path = backup.make_backup(seeded)
    manifest = backup.verify_backup(path, seeded)
    assert manifest["files"]["uploads.zip"]["entries"] == 1          # черновик из staging не попал
    assert not list((tmp_path / "backups").glob("*.partial"))
    assert backup.list_backups(seeded.backup_path) == [path]


def test_corrupted_copy_is_detected(seeded):
    path = backup.make_backup(seeded)
    with (path / "db.dump").open("ab") as fh:
        fh.write(b"junk")
    with pytest.raises(backup.BackupError, match="повреждён"):
        backup.verify_backup(path, seeded)


def test_restore_round_trip(seeded, tmp_path):
    path = backup.make_backup(seeded)
    psql(seeded, "DELETE FROM users")
    psql(seeded, "INSERT INTO users (login, password_hash, display_name) VALUES ('after1', 'x', 'After')")
    (tmp_path / "uploads" / "venues" / "a.jpg").unlink()
    (tmp_path / "uploads" / "venues" / "late.jpg").write_bytes(b"late")
    backup.restore_backup(seeded, path, assume_yes=True)
    assert logins(seeded) == "before1"
    assert (tmp_path / "uploads" / "venues" / "a.jpg").read_bytes() == b"photo-a"
    assert not (tmp_path / "uploads" / "venues" / "late.jpg").exists()
    assert list(tmp_path.glob("uploads.before_restore_*"))             # прежняя папка сохранена, а не удалена
    assert len(backup.list_backups(seeded.backup_path)) == 2           # исходная + страховочная


def test_restore_refuses_while_server_runs(seeded, tmp_path):
    path = backup.make_backup(seeded)
    (tmp_path / "data" / "server.pid").write_text(str(os.getpid()))
    with pytest.raises(backup.BackupError, match="Сервер запущен"):
        backup.restore_backup(seeded, path, assume_yes=True)
    assert logins(seeded) == "before1"                                  # ничего не изменилось


def test_restore_without_confirmation_changes_nothing(seeded, monkeypatch):
    path = backup.make_backup(seeded)
    psql(seeded, "DELETE FROM users")
    monkeypatch.setattr("builtins.input", lambda *_: "нет")
    backup.restore_backup(seeded, path)
    assert logins(seeded) == ""


def test_retention_keeps_minimum_and_removes_only_old(seeded):
    path = backup.make_backup(seeded)
    root = seeded.backup_path
    old_names = [(datetime.now() - timedelta(days=d)).strftime("sportcourts_%Y%m%d_%H%M%S") for d in (40, 30, 20)]
    for name in old_names:
        shutil.copytree(path, root / name)
    (root / "not_a_backup").mkdir()                                     # чужие папки не трогаем
    removed = backup.apply_retention(seeded)
    names = {p.name for p in backup.list_backups(root)}
    assert removed == 2 and path.name in names and old_names[2] in names     # 2 самых новых из старых + свежая = минимум 2
    assert (root / "not_a_backup").exists()


def test_not_enough_disk_space_is_reported(seeded, monkeypatch):
    class Usage:
        total, used, free = 100, 99, 1
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda p: Usage)
    with pytest.raises(backup.BackupError, match="Недостаточно места"):
        backup.make_backup(seeded)
    assert not list(seeded.backup_path.glob("*"))
