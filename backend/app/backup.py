"""Резервное копирование и восстановление.

    python -m app.backup backup                 создать копию (база + фотографии) в BACKUP_DIR
    python -m app.backup list                   показать имеющиеся копии
    python -m app.backup verify [КОПИЯ]         проверить целостность копии (по умолчанию — последней)
    python -m app.backup restore КОПИЯ [--yes]  восстановить; ПЕРЕЗАПИСЫВАЕТ текущие данные

Копия — каталог sportcourts_ГГГГММДД_ЧЧММСС с файлами db.dump (pg_dump, формат custom),
uploads.zip (фотографии) и manifest.json (размеры, контрольные суммы, версия).

ВАЖНО: копия на том же физическом диске, что и рабочие данные, не защищает от поломки самого диска.
Укажите в BACKUP_DIR путь на другом диске или регулярно копируйте каталог на внешний носитель.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.engine import make_url

from . import __version__
from .config import ConfigError, Settings, load_settings
from .run import pid_alive

logger = logging.getLogger("sportcourts.backup")
NAME_RE = re.compile(r"^sportcourts_\d{8}_\d{6}$")
GB = 1024 ** 3


class BackupError(Exception):
    """Понятная пользователю ошибка (выводится без трассировки)."""


# ----------------------------------------------------------------------------- вспомогательное
def find_pg_tool(settings: Settings, tool: str) -> str:
    exe = tool + (".exe" if os.name == "nt" else "")
    candidates: list[Path] = []
    if settings.pg_bin_dir:
        explicit = Path(settings.pg_bin_dir) / exe
        if explicit.is_file():
            return str(explicit)  # явно заданная папка важнее PATH
    found = shutil.which(tool)
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            root = Path(base) / "PostgreSQL"
            if root.is_dir():
                for ver in sorted(root.iterdir(), reverse=True):
                    candidates.append(ver / "bin" / exe)
    else:
        for ver in sorted(Path("/usr/lib/postgresql").glob("*"), reverse=True):
            candidates.append(ver / "bin" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    raise BackupError(
        f"Не найдена программа {tool}. Установите PostgreSQL вместе с «Command Line Tools» либо укажите папку bin "
        f"в .env: PG_BIN_DIR=C:\\Program Files\\PostgreSQL\\17\\bin"
    )


def pg_env(settings: Settings) -> tuple[dict[str, str], list[str]]:
    """Переменные окружения и аргументы подключения. Пароль передаётся через PGPASSWORD, а не в командной строке."""
    url = make_url(settings.database_url)
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    env["PGCLIENTENCODING"] = "UTF8"
    args = ["--host", url.host or "127.0.0.1", "--port", str(url.port or 5432), "--username", url.username or "postgres"]
    return env, args


def db_name(settings: Settings) -> str:
    name = make_url(settings.database_url).database
    if not name:
        raise BackupError("В DATABASE_URL не указано имя базы данных.")
    return name


def run_tool(cmd: list[str], env: dict[str, str], what: str) -> str:
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise BackupError(f"Не удалось запустить {what}: {exc}") from exc
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-6:]
        raise BackupError(f"{what} завершился с ошибкой (код {res.returncode}):\n  " + "\n  ".join(tail))
    return res.stdout


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0


def db_size(settings: Settings, env: dict[str, str], conn: list[str]) -> int:
    out = run_tool([find_pg_tool(settings, "psql"), *conn, "--dbname", db_name(settings), "-At", "-c",
                    "SELECT pg_database_size(current_database())"], env, "psql")
    return int(out.strip() or 0)


def list_backups(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and NAME_RE.match(p.name) and (p / "manifest.json").is_file()),
                  key=lambda p: p.name)


def human(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def check_free_space(target: Path, need: int, settings: Settings) -> None:
    target.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(target).free
    # запас: сжатие обычно уменьшает размер, но берём худший случай + 10 %
    required = int(need * 1.1)
    if free < required:
        raise BackupError(f"Недостаточно места для копии: нужно примерно {human(required)}, свободно {human(free)} "
                          f"(папка {target}). Освободите место или смените BACKUP_DIR.")
    if free - required < settings.min_free_disk_gb * GB:
        print(f"ВНИМАНИЕ: после копии на диске останется меньше {settings.min_free_disk_gb:g} ГБ свободного места.")


# ----------------------------------------------------------------------------- создание копии
def make_backup(settings: Settings, label: str = "") -> Path:
    root = settings.backup_path
    env, conn = pg_env(settings)
    pg_dump = find_pg_tool(settings, "pg_dump")
    pg_restore = find_pg_tool(settings, "pg_restore")
    uploads = settings.uploads_path
    need = db_size(settings, env, conn) + dir_size(uploads)
    check_free_space(root, need, settings)

    while True:                                # имя содержит секунды; если копия в эту секунду уже есть — ждём следующую
        name = "sportcourts_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        final = root / name
        work = root / (name + ".partial")      # недокопированное не принимается за копию
        if not final.exists() and not work.exists():
            break
        time.sleep(1)
    work.mkdir(parents=True)
    try:
        dump = work / "db.dump"
        print("Копирование базы данных…")
        run_tool([pg_dump, *conn, "--format=custom", "--no-owner", "--file", str(dump), db_name(settings)], env, "pg_dump")
        # проверка: из файла можно прочитать оглавление
        toc = run_tool([pg_restore, "--list", str(dump)], env, "pg_restore --list")
        if "TABLE DATA" not in toc:
            raise BackupError("Дамп базы не содержит данных таблиц — копия отброшена.")

        print("Копирование фотографий…")
        archive = work / "uploads.zip"
        count = 0
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:   # JPEG уже сжаты
            if uploads.is_dir():
                for f in sorted(uploads.rglob("*")):
                    if f.is_file() and "staging" not in f.relative_to(uploads).parts:   # черновики не нужны
                        zf.write(f, f.relative_to(uploads).as_posix())
                        count += 1
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                raise BackupError("Архив фотографий повреждён — копия отброшена.")

        manifest = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "app_version": __version__, "database": db_name(settings), "label": label,
            "files": {
                "db.dump": {"bytes": dump.stat().st_size, "sha256": sha256(dump)},
                "uploads.zip": {"bytes": archive.stat().st_size, "sha256": sha256(archive), "entries": count},
            },
        }
        (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        work.rename(final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    print(f"Готово: {final}")
    print(f"  база: {human(manifest['files']['db.dump']['bytes'])}, фотографий: {count} ({human(manifest['files']['uploads.zip']['bytes'])})")
    removed = apply_retention(settings)
    if removed:
        print(f"Удалено устаревших копий: {removed}")
    same_drive = _same_drive(root, settings.data_path)
    if same_drive:
        print("ПОМНИТЕ: копия лежит на том же диске, что и данные сервера. От поломки диска она не защитит — "
              "копируйте папку с копиями на другой диск или внешний носитель.")
    logger.info("Создана резервная копия %s", final)
    return final


def _same_drive(a: Path, b: Path) -> bool:
    try:
        if os.name == "nt":
            return a.resolve().drive.lower() == b.resolve().drive.lower()
        return os.stat(a).st_dev == os.stat(b if b.exists() else b.parent).st_dev
    except OSError:
        return True


def apply_retention(settings: Settings) -> int:
    """Удаляет копии старше BACKUP_RETENTION_DAYS, но всегда оставляет BACKUP_MIN_KEEP самых новых."""
    backups = list_backups(settings.backup_path)
    keep = max(settings.backup_min_keep, 1)
    if len(backups) <= keep:
        return 0
    limit = datetime.now() - timedelta(days=settings.backup_retention_days)
    removed = 0
    for path in backups[:-keep]:
        try:
            stamp = datetime.strptime(path.name[len("sportcourts_"):], "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if stamp < limit:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


# ----------------------------------------------------------------------------- проверка
def verify_backup(path: Path, settings: Settings | None = None) -> dict:
    manifest_file = path / "manifest.json"
    if not manifest_file.is_file():
        raise BackupError(f"{path} не похож на резервную копию (нет manifest.json).")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    for fname, meta in manifest["files"].items():
        f = path / fname
        if not f.is_file():
            raise BackupError(f"В копии нет файла {fname}.")
        if f.stat().st_size != meta["bytes"] or sha256(f) != meta["sha256"]:
            raise BackupError(f"Файл {fname} повреждён (контрольная сумма не совпала).")
    with zipfile.ZipFile(path / "uploads.zip") as zf:
        if zf.testzip() is not None:
            raise BackupError("Архив фотографий повреждён.")
    if settings is not None:
        env, _ = pg_env(settings)
        run_tool([find_pg_tool(settings, "pg_restore"), "--list", str(path / "db.dump")], env, "pg_restore --list")
    return manifest


def resolve_backup(settings: Settings, arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if not p.is_absolute() and not p.exists():
            p = settings.backup_path / arg
        return p
    backups = list_backups(settings.backup_path)
    if not backups:
        raise BackupError(f"В {settings.backup_path} нет резервных копий.")
    return backups[-1]


# ----------------------------------------------------------------------------- восстановление
def server_running(settings: Settings) -> bool:
    pid_file = settings.data_path / "server.pid"
    if not pid_file.is_file():
        return False
    try:
        return pid_alive(int(pid_file.read_text().strip()))
    except (ValueError, OSError):
        return False


def restore_backup(settings: Settings, path: Path, assume_yes: bool = False, safety_copy: bool = True) -> None:
    manifest = verify_backup(path, settings)
    if server_running(settings):
        raise BackupError("Сервер запущен. Остановите его (stop.bat) и повторите восстановление.")
    uploads = settings.uploads_path
    env, conn = pg_env(settings)
    print("=" * 70)
    print("ВОССТАНОВЛЕНИЕ ИЗ РЕЗЕРВНОЙ КОПИИ")
    print(f"  копия:   {path.name}  (создана {manifest['created_at']})")
    print(f"  база:    {db_name(settings)} — ВСЕ ТЕКУЩИЕ ДАННЫЕ БУДУТ ЗАМЕНЕНЫ данными из копии")
    print(f"  фото:    {uploads} — текущая папка будет переименована, а не удалена")
    print("  Всё, что появилось после создания копии (пользователи, площадки, сообщения, фото), будет потеряно.")
    if safety_copy:
        print("  Перед этим будет создана страховочная копия текущего состояния.")
    print("=" * 70)
    if not assume_yes:
        answer = input("Для продолжения введите слово ВОССТАНОВИТЬ: ").strip()
        if answer != "ВОССТАНОВИТЬ":
            print("Отменено. Ничего не изменено.")
            return

    # место: страховочная копия + распакованные фото + запас
    need = manifest["files"]["db.dump"]["bytes"] * 3 + manifest["files"]["uploads.zip"]["bytes"] * 2
    if safety_copy:
        need += db_size(settings, env, conn) + dir_size(uploads)
    check_free_space(settings.backup_path, need // 2, settings)
    check_free_space(uploads.parent, manifest["files"]["uploads.zip"]["bytes"] * 2, settings)

    if safety_copy:
        print("Страховочная копия текущего состояния…")
        safety = make_backup(settings, label="before-restore")
        print(f"  (если восстановление окажется ошибкой, вернуться можно командой: restore {safety.name})")

    staging = uploads.parent / (uploads.name + ".restore_tmp")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(path / "uploads.zip") as zf:
            for member in zf.namelist():
                target = (staging / member).resolve()
                if staging.resolve() not in target.parents:       # защита от «../» в архиве
                    raise BackupError(f"Небезопасный путь в архиве: {member}")
            zf.extractall(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("Восстановление базы данных…")
    run_tool([find_pg_tool(settings, "pg_restore"), *conn, "--dbname", db_name(settings), "--clean", "--if-exists",
              "--no-owner", "--exit-on-error", str(path / "db.dump")], env, "pg_restore")

    print("Восстановление фотографий…")
    if uploads.exists():
        aside = uploads.parent / f"{uploads.name}.before_restore_{datetime.now():%Y%m%d_%H%M%S}"
        uploads.rename(aside)
        print(f"  прежняя папка сохранена как {aside.name} (удалите её вручную, когда убедитесь, что всё в порядке)")
    staging.rename(uploads)

    # копия могла быть сделана на более старой версии схемы — приводим базу к актуальной
    print("Проверка версии схемы базы…")
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_env = {**os.environ, "DATABASE_URL": settings.database_url, "SECRET_KEY": settings.secret_key}
    res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, env=alembic_env,
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise BackupError("Данные восстановлены, но обновить схему не удалось:\n  " + (res.stderr or res.stdout).strip()[-400:])
    print("Готово. Запустите сервер (start.bat) и проверьте данные.")
    logger.info("Восстановление из %s выполнено", path)


# ----------------------------------------------------------------------------- командная строка
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup")
    sub.add_parser("list")
    p = sub.add_parser("verify")
    p.add_argument("name", nargs="?")
    p = sub.add_parser("restore")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true", help="не спрашивать подтверждение (для автоматизации)")
    p.add_argument("--no-safety-copy", action="store_true", help="не делать страховочную копию перед восстановлением")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"\nОШИБКА НАСТРОЕК: {exc}\n", file=sys.stderr)
        return 2
    try:
        if args.cmd == "backup":
            make_backup(settings)
        elif args.cmd == "list":
            items = list_backups(settings.backup_path)
            if not items:
                print(f"В {settings.backup_path} резервных копий нет.")
            for p_ in items:
                m = json.loads((p_ / "manifest.json").read_text(encoding="utf-8"))
                total = sum(v["bytes"] for v in m["files"].values())
                print(f"{p_.name}  {human(total):>10}  {m.get('label') or ''}")
        elif args.cmd == "verify":
            path = resolve_backup(settings, args.name)
            verify_backup(path, settings)
            print(f"Копия {path.name} исправна (контрольные суммы совпали, дамп читается).")
        elif args.cmd == "restore":
            restore_backup(settings, resolve_backup(settings, args.name), assume_yes=args.yes, safety_copy=not args.no_safety_copy)
    except BackupError as exc:
        print(f"\nОШИБКА: {exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
