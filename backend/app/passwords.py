"""Хеширование паролей (Argon2id). Пароль в открытом виде нигде не хранится и не логируется."""
from __future__ import annotations

import asyncio
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Параметры по умолчанию argon2-cffi соответствуют рекомендациям RFC 9106 (low-memory profile).
_hasher = PasswordHasher()

# Хеш «пустышка» для выравнивания времени ответа, когда логин не найден.
_DUMMY_HASH = _hasher.hash("sportcourts-dummy-password")

UNUSABLE_HASH = "!"  # значение для удалённых аккаунтов: никакой пароль не подойдёт


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await asyncio.to_thread(verify_password, password_hash, password)


async def burn_dummy_verify(password: str) -> None:
    """Тратит столько же времени, сколько реальная проверка (защита от перебора логинов по времени)."""
    await asyncio.to_thread(verify_password, _DUMMY_HASH, password)


def generate_temporary_password(length: int = 12) -> str:
    """Случайный временный пароль без похожих символов (0/O, 1/l/I)."""
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(length))
