"""Логирование: файл с ротацией + консоль, секреты маскируются."""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    # Authorization: Bearer xxx / Bearer xxx
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]+"), "Bearer ***"),
    # JWT целиком (три base64url-части)
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*"), "***jwt***"),
    # password=..., "password": "...", token: ..., secret_key=...
    (
        re.compile(r"(?i)((?:pass(?:word|wd)?|token|secret(?:_key)?|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?)([^\s\"',;&}]+)"),
        r"\1***",
    ),
    # пароль внутри URL подключения: scheme://user:password@host
    (re.compile(r"(://[^:/@\s]+:)([^@\s]+)(@)"), r"\1***\3"),
]


def redact(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    """Маскирует пароли, токены и ключи в итоговом тексте записи (включая traceback)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - некорректный формат не должен ронять приложение
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        if record.exc_info:
            formatted = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact(formatted)
            record.exc_info = None
        return True


_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(logs_dir: Path, level: str = "INFO", max_mb: int = 5, backup_count: int = 5) -> Path:
    """Настраивает корневой логгер. Повторный вызов безопасен (старые обработчики заменяются)."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "sportcourts.log"

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_sportcourts", False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_FORMAT)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_mb * 1024 * 1024, backupCount=backup_count, encoding="utf-8"
    )
    console = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, console):
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        handler._sportcourts = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    return log_file
