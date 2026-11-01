"""Настройки приложения.

Значения читаются из файла .env в корне репозитория; переменные окружения
процесса имеют приоритет над файлом. Все секреты задаются только здесь —
в исходном коде их нет.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, ValidationError

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DEFAULT_ENV_FILE = REPO_DIR / ".env"

PLACEHOLDER_MARKERS = ("CHANGE_ME", "changeme", "change-me", "<")


class ConfigError(RuntimeError):
    """Ошибка конфигурации с понятным пользователю сообщением."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    # --- запуск
    app_env: str = "production"
    host: str = "127.0.0.1"
    port: int = 8000
    trusted_proxy_ips: str = "127.0.0.1"

    # --- секреты (обязательные)
    database_url: str
    secret_key: str

    # --- сессии и онлайн-статус
    access_token_days: int = 30
    online_timeout_seconds: int = 120

    # --- пути (относительные пути считаются от корня репозитория)
    uploads_dir: str = "data/uploads"
    logs_dir: str = "data/logs"
    data_dir: str = "data"
    backup_dir: str = "backups"

    # --- логи
    log_level: str = "INFO"
    log_max_mb: int = 5
    log_backup_count: int = 5

    # --- первый администратор (используется только командой create-admin)
    admin_login: str = ""
    admin_password: str = ""

    # --- изображения
    max_upload_mb: int = 5
    max_request_mb: int = 8
    image_max_dimension: int = 1600
    avatar_max_dimension: int = 512
    jpeg_quality: int = 82
    image_max_pixels: int = 40_000_000
    staging_ttl_hours: int = 24

    # --- присутствие, отчёты, игры
    presence_ttl_hours: int = 3
    player_report_ttl_hours: int = 6
    player_report_cooldown_seconds: int = 300
    player_report_max_per_hour: int = 20
    game_list_grace_hours: int = 12
    max_open_games_per_user: int = 5
    max_pending_submissions_per_user: int = 5

    # --- защита от перебора
    login_max_attempts: int = 8
    login_window_seconds: int = 300
    register_max_per_ip: int = 10
    register_window_seconds: int = 600
    message_max_per_minute: int = 40

    # --- база данных
    db_pool_size: int = 5
    db_max_overflow: int = 5
    pg_bin_dir: str = ""

    # --- резервные копии и диск
    backup_retention_days: int = 14
    backup_min_keep: int = 3
    min_free_disk_gb: float = 5.0

    # ------------------------------------------------------------ вычисляемые
    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    def resolve_path(self, value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else (REPO_DIR / p)

    @property
    def uploads_path(self) -> Path:
        return self.resolve_path(self.uploads_dir)

    @property
    def logs_path(self) -> Path:
        return self.resolve_path(self.logs_dir)

    @property
    def data_path(self) -> Path:
        return self.resolve_path(self.data_dir)

    @property
    def backup_path(self) -> Path:
        return self.resolve_path(self.backup_dir)


def _normalize_database_url(url: str) -> str:
    url = url.strip()
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def load_settings(env_file: Path | str | None = None, environ: dict[str, str] | None = None) -> Settings:
    """Собирает настройки из .env и окружения. Бросает ConfigError с понятным текстом."""
    env_path = Path(env_file) if env_file else Path(os.environ.get("SPORTCOURTS_ENV_FILE", DEFAULT_ENV_FILE))
    raw: dict[str, Any] = {}
    if env_path.is_file():
        raw.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    raw.update(environ if environ is not None else os.environ)

    # Имена полей — в нижнем регистре, переменные окружения — в верхнем.
    fields = set(Settings.model_fields)
    data: dict[str, Any] = {}
    for key, value in raw.items():
        name = key.lower()
        if name in fields and value != "":
            data[name] = value

    missing = [n.upper() for n in ("database_url", "secret_key") if n not in data]
    if missing:
        raise ConfigError(
            f"Не заданы обязательные настройки: {', '.join(missing)}. "
            f"Скопируйте .env.example в .env и заполните значения (ищу файл: {env_path})."
        )

    data["database_url"] = _normalize_database_url(data["database_url"])
    try:
        settings = Settings(**data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']).upper()}: {e['msg']}" for e in exc.errors()
        )
        raise ConfigError(f"Некорректные настройки в .env: {problems}") from exc

    _validate_semantics(settings)
    return settings


def _validate_semantics(s: Settings) -> None:
    if not s.database_url.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
        raise ConfigError("DATABASE_URL должен начинаться с postgresql+asyncpg:// (или postgresql://).")
    if len(s.secret_key) < 32:
        raise ConfigError("SECRET_KEY слишком короткий: нужно не меньше 32 символов. Сгенерируйте его командой из README.")
    if any(marker.lower() in s.secret_key.lower() for marker in PLACEHOLDER_MARKERS):
        raise ConfigError("SECRET_KEY содержит значение-заглушку из .env.example. Задайте настоящий случайный ключ.")
    if not (1 <= s.port <= 65535):
        raise ConfigError("PORT должен быть от 1 до 65535.")
    if s.access_token_days < 1:
        raise ConfigError("ACCESS_TOKEN_DAYS должен быть не меньше 1.")
    if not (1 <= s.jpeg_quality <= 95):
        raise ConfigError("JPEG_QUALITY должен быть от 1 до 95.")
    if s.max_upload_mb < 1 or s.max_request_mb < s.max_upload_mb:
        raise ConfigError("MAX_REQUEST_MB не может быть меньше MAX_UPLOAD_MB, а MAX_UPLOAD_MB — меньше 1.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
