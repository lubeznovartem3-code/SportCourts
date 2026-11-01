"""Хранилище загруженных фотографий на локальном диске.

Структура каталога UPLOADS_DIR:
    avatars/   готовые аватары пользователей
    venues/    готовые фотографии площадок
    staging/   «черновики»: загруженное, но ещё не прикреплённое к записи

Имена файлов генерируются сервером (случайный UUID), имя от клиента не используется.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path

logger = logging.getLogger("sportcourts.files")

KINDS = ("avatars", "venues")
_FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")
_TOKEN_RE = re.compile(r"^(\d{1,18})_([0-9a-f]{32})$")


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.staging = self.root / "staging"
        for kind in (*KINDS, "staging"):
            (self.root / kind).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ запись
    def _write_atomic(self, directory: Path, filename: str, data: bytes) -> None:
        """Пишет во временный файл и переименовывает; при ошибке временный файл удаляется."""
        final = directory / filename
        tmp = directory / f".{filename}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, final)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def save(self, kind: str, data: bytes) -> str:
        """Сохраняет готовый JPEG в каталог kind и возвращает имя файла."""
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        filename = f"{uuid.uuid4().hex}.jpg"
        self._write_atomic(self.root / kind, filename, data)
        return filename

    def stage(self, owner_id: int, data: bytes) -> str:
        """Кладёт файл в staging и возвращает токен вида '<owner_id>_<uuid>'."""
        name = uuid.uuid4().hex
        self._write_atomic(self.staging, f"{owner_id}_{name}.jpg", data)
        return f"{owner_id}_{name}"

    def adopt(self, token: str, owner_id: int, kind: str) -> str | None:
        """Переносит файл из staging в каталог kind. None — токен неверный/чужой/устарел."""
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        m = _TOKEN_RE.match(token or "")
        if not m or int(m.group(1)) != owner_id:
            return None
        source = self.staging / f"{token}.jpg"
        if not source.is_file():
            return None
        filename = f"{m.group(2)}.jpg"
        try:
            os.replace(source, self.root / kind / filename)
        except OSError:
            logger.exception("Не удалось перенести файл из staging")
            return None
        return filename

    # ------------------------------------------------------------------ чтение/удаление
    def resolve(self, kind: str, filename: str) -> Path | None:
        """Безопасно находит файл: строгая проверка имени исключает выход за пределы каталога."""
        if kind not in KINDS or not _FILENAME_RE.match(filename or ""):
            return None
        path = self.root / kind / filename
        return path if path.is_file() else None

    def delete(self, kind: str, filename: str | None) -> None:
        if not filename or kind not in KINDS or not _FILENAME_RE.match(filename):
            return
        try:
            (self.root / kind / filename).unlink(missing_ok=True)
        except OSError:
            logger.warning("Не удалось удалить файл %s/%s", kind, filename)

    def cleanup_staging(self, max_age_hours: float) -> int:
        """Удаляет устаревшие черновики и «осиротевшие» временные файлы. Возвращает их число."""
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        for path in self.staging.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                logger.warning("Не удалось обработать %s при очистке", path.name)
        return removed


def media_url(kind: str, filename: str | None) -> str | None:
    return f"/media/{kind}/{filename}" if filename else None
