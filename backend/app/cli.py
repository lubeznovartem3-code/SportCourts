"""Служебные команды сервера.

    python -m app.cli create-admin       создать первого администратора (идемпотентно)
    python -m app.cli reset-password ЛОГИН   задать новый пароль (в т.ч. администратору)
    python -m app.cli check              проверить настройки, базу, миграции, каталоги и свободное место
    python -m app.cli cleanup            удалить устаревшие черновики фото
    python -m app.cli stop               корректно остановить запущенный сервер (то же делает stop.bat)
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import shutil
import sys
import time

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import __version__, passwords, validators
from .config import ConfigError, Settings, load_settings
from .db import check_collation, check_database, make_engine
from .files import FileStore


def _fail(message: str, code: int = 1) -> int:
    print(f"\nОШИБКА: {message}", file=sys.stderr)
    return code


def _ask_password(prompt: str = "Пароль администратора") -> str:
    while True:
        first = getpass.getpass(f"{prompt} (не короче {validators.PASSWORD_MIN} символов, ввод скрыт): ")
        try:
            validators.validate_password(first)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        if getpass.getpass("Повторите пароль: ") != first:
            print("  Пароли не совпали, попробуйте ещё раз.")
            continue
        return first


async def create_admin(settings: Settings, login: str | None = None, password: str | None = None,
                       interactive: bool = True) -> tuple[str, str]:
    """Возвращает (статус, сообщение). Статусы: created | exists | error. Повторный вызов ничего не меняет."""
    engine = make_engine(settings)
    try:
        raw_login = login or settings.admin_login
        if not raw_login:
            return "error", "Не задан ADMIN_LOGIN в .env (или передайте --login)."
        try:
            raw_login = validators.validate_login(raw_login)
        except ValueError as exc:
            return "error", f"Некорректный ADMIN_LOGIN: {exc}"
        from_file = False
        if password is None:
            if settings.admin_password:
                password, from_file = settings.admin_password, True
            elif interactive:
                password = _ask_password()
            else:
                return "error", "Не задан ADMIN_PASSWORD в .env."
        try:
            validators.validate_password(password)
        except ValueError as exc:
            return "error", f"Некорректный пароль администратора: {exc}"
        async with engine.begin() as conn:
            existing = (await conn.execute(
                text("SELECT id, role FROM users WHERE login = :l"), {"l": raw_login})).first()
            if existing is not None:
                note = "уже существует" if existing[1] == "admin" else f"уже занят обычным пользователем (роль {existing[1]})"
                return "exists", (f"Пользователь «{raw_login}» {note}. Ничего не изменено "
                                  "(пароль не перезаписывается; для сброса используйте reset-password).")
            ph = await passwords.hash_password_async(password)
            try:
                await conn.execute(
                    text("INSERT INTO users (login, password_hash, display_name, role, must_change_password) "
                         "VALUES (:l, :ph, :dn, 'admin', :mc)"),
                    {"l": raw_login, "ph": ph, "dn": "Администратор", "mc": from_file})
            except IntegrityError:
                return "exists", f"Пользователь «{raw_login}» уже существует. Ничего не изменено."
            await conn.execute(text("INSERT INTO audit_log (action, target_type, details) "
                                    "VALUES ('admin_created', 'user', :d)"), {"d": f"login={raw_login} via cli"})
        extra = (" Пароль взят из .env, поэтому при первом входе потребуется сменить его. "
                 "После этого удалите ADMIN_PASSWORD из .env.") if from_file else ""
        return "created", f"Администратор «{raw_login}» создан.{extra}"
    finally:
        await engine.dispose()


async def reset_password(settings: Settings, login: str, password: str | None) -> tuple[bool, str]:
    engine = make_engine(settings)
    try:
        async with engine.begin() as conn:
            row = (await conn.execute(text("SELECT id FROM users WHERE login = :l AND deleted_at IS NULL"),
                                      {"l": login})).first()
            if row is None:
                return False, f"Пользователь «{login}» не найден (логин чувствителен к регистру)."
            temp = False
            if password is None:
                password, temp = passwords.generate_temporary_password(), True
            validators.validate_password(password)
            await conn.execute(
                text("UPDATE users SET password_hash = :ph, must_change_password = :mc WHERE id = :id"),
                {"ph": await passwords.hash_password_async(password), "mc": temp, "id": row[0]})
            await conn.execute(text("UPDATE user_sessions SET revoked_at = now() WHERE user_id = :id AND revoked_at IS NULL"),
                               {"id": row[0]})
            await conn.execute(text("INSERT INTO audit_log (action, target_type, target_id, details) "
                                    "VALUES ('password_reset', 'user', :id, 'via cli')"), {"id": row[0]})
        if temp:
            return True, f"Временный пароль для «{login}»: {password}\nПри первом входе пользователь обязан его сменить."
        return True, f"Пароль пользователя «{login}» изменён."
    finally:
        await engine.dispose()


def stop_server(settings: Settings, timeout: float = 20.0) -> tuple[bool, str]:
    """Просит сервер завершиться через файл data/stop.flag (так приложение закрывается штатно) и ждёт."""
    from .run import pid_alive
    data = settings.data_path
    pid_file, flag = data / "server.pid", data / "stop.flag"
    if not pid_file.is_file():
        return True, "Сервер не запущен."
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return True, "Сервер не запущен (удалён повреждённый файл PID)."
    if not pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        return True, "Сервер не запущен (удалён устаревший файл PID после аварийного завершения)."
    flag.write_text("stop")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            pid_file.unlink(missing_ok=True)
            flag.unlink(missing_ok=True)
            return True, "Сервер остановлен."
        time.sleep(0.3)
    flag.unlink(missing_ok=True)
    return False, (f"Сервер (PID {pid}) не остановился за {timeout:g} с. Закройте окно сервера или завершите процесс вручную: "
                   f"taskkill /PID {pid} /F")


async def run_check(settings: Settings) -> int:
    problems = 0

    def line(ok: bool, text_: str) -> None:
        nonlocal problems
        print(("[ OK ] " if ok else "[FAIL] ") + text_)
        problems += 0 if ok else 1

    print(f"SportCourts {__version__} — проверка окружения\n")
    line(True, f"Настройки .env прочитаны (режим: {settings.app_env})")
    engine = make_engine(settings)
    try:
        ok, reason = await check_database(engine)
        line(ok, "Подключение к PostgreSQL" + ("" if ok else f" не удалось ({reason}). Запущена ли служба PostgreSQL? Верны ли DATABASE_URL и пароль?"))
        if ok:
            try:
                async with engine.connect() as conn:
                    rev = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                from .main import HEAD_REVISION
                line(rev == HEAD_REVISION, f"Миграции: версия базы {rev}, ожидается {HEAD_REVISION}"
                     + ("" if rev == HEAD_REVISION else " — выполните: alembic upgrade head"))
            except Exception:  # noqa: BLE001
                line(False, "Миграции не применены — выполните: alembic upgrade head")
            line(await check_collation(engine), "Регистронезависимый поиск кириллицы в БД"
                 " (если FAIL — создайте базу по docs/POSTGRESQL.md с ICU-локалью)")
            try:
                async with engine.connect() as conn:
                    admins = (await conn.execute(text("SELECT count(*) FROM users WHERE role = 'admin' AND deleted_at IS NULL"))).scalar()
                line(bool(admins), f"Администраторов в базе: {admins}" + ("" if admins else " — выполните: python -m app.cli create-admin"))
            except Exception:  # noqa: BLE001
                pass
    finally:
        await engine.dispose()
    try:
        FileStore(settings.uploads_path)
        line(True, f"Каталог фотографий доступен для записи: {settings.uploads_path}")
    except OSError as exc:
        line(False, f"Каталог фотографий недоступен: {exc}")
    free_gb = shutil.disk_usage(settings.uploads_path if settings.uploads_path.exists() else settings.resolve_path(".")).free / 1024 ** 3
    line(free_gb >= settings.min_free_disk_gb, f"Свободное место на диске: {free_gb:.1f} ГБ (порог {settings.min_free_disk_gb:g} ГБ)")
    print("\nИтог:", "всё в порядке" if problems == 0 else f"проблем: {problems}")
    return 0 if problems == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--login")
    sub.add_parser("check")
    sub.add_parser("cleanup")
    sub.add_parser("stop")
    p = sub.add_parser("reset-password")
    p.add_argument("login")
    p.add_argument("--temporary", action="store_true", help="сгенерировать временный пароль (потребует смены при входе)")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        return _fail(str(exc), 2)

    try:
        if args.command == "create-admin":
            status, message = asyncio.run(create_admin(settings, login=args.login))
            print(message)
            return 1 if status == "error" else 0
        if args.command == "reset-password":
            pw = None if args.temporary else _ask_password("Новый пароль")
            ok, message = asyncio.run(reset_password(settings, args.login, pw))
            print(message)
            return 0 if ok else 1
        if args.command == "check":
            return asyncio.run(run_check(settings))
        if args.command == "stop":
            ok, message = stop_server(settings)
            print(message)
            return 0 if ok else 1
        if args.command == "cleanup":
            removed = FileStore(settings.uploads_path).cleanup_staging(settings.staging_ttl_hours)
            print(f"Удалено устаревших временных файлов: {removed}")
            return 0
    except (OSError, ConnectionError) as exc:
        return _fail(f"{type(exc).__name__}: нет связи с базой данных. Проверьте, что PostgreSQL запущен и DATABASE_URL верен.")
    except Exception as exc:  # noqa: BLE001
        from sqlalchemy.exc import SQLAlchemyError
        if isinstance(exc, SQLAlchemyError):
            return _fail("Ошибка базы данных (" + type(exc).__name__ + "). Проверьте, что PostgreSQL запущен, миграции применены "
                         "(alembic upgrade head) и DATABASE_URL верен.")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
