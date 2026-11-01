"""Чистые функции проверки пользовательского ввода (без зависимостей от БД и веб-слоя).

Правила (см. ТЗ, раздел 6):
  * логин уникален с учётом регистра, 3–32 символа: буквы (в т.ч. кириллица), цифры
    и распространённые символы  _ . - @ + ! # $ % & * ~
  * пароль — не короче 8 символов, других требований к составу нет.
"""
from __future__ import annotations

import unicodedata

LOGIN_MIN = 3
LOGIN_MAX = 32
PASSWORD_MIN = 8
PASSWORD_MAX = 128
DISPLAY_NAME_MAX = 64

_ALLOWED_PUNCT = set("_.-@+!#$%&*~")


def normalize_login(value: str) -> str:
    """Приводит логин к NFC, чтобы визуально одинаковые строки были одинаковыми байтами.

    Регистр НЕ меняется: «Alex» и «alex» — разные логины.
    """
    return unicodedata.normalize("NFC", value.strip())


def validate_login(value: str) -> str:
    login = normalize_login(value)
    if not (LOGIN_MIN <= len(login) <= LOGIN_MAX):
        raise ValueError(f"Логин должен содержать от {LOGIN_MIN} до {LOGIN_MAX} символов")
    for ch in login:
        if ch.isalnum() or ch in _ALLOWED_PUNCT:
            continue
        raise ValueError("Логин может содержать только буквы, цифры и символы _ . - @ + ! # $ % & * ~")
    return login


def validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"Пароль должен содержать не меньше {PASSWORD_MIN} символов")
    if len(value) > PASSWORD_MAX:
        raise ValueError(f"Пароль не должен быть длиннее {PASSWORD_MAX} символов")
    if "\x00" in value:
        raise ValueError("Пароль содержит недопустимый символ")
    return value


def validate_display_name(value: str) -> str:
    name = " ".join(unicodedata.normalize("NFC", value).split())
    if not name:
        raise ValueError("Имя не может быть пустым")
    if len(name) > DISPLAY_NAME_MAX:
        raise ValueError(f"Имя не должно быть длиннее {DISPLAY_NAME_MAX} символов")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise ValueError("Имя содержит недопустимые символы")
    return name


def clean_text(value: str | None, max_len: int, field: str = "Текст") -> str | None:
    """Обрезает пробелы; пустая строка превращается в None; контролирует длину."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value).strip()
    if not text:
        return None
    if len(text) > max_len:
        raise ValueError(f"{field}: не больше {max_len} символов")
    if any(unicodedata.category(ch) in ("Cc", "Cs") and ch not in "\n\t" for ch in text):
        raise ValueError(f"{field}: недопустимые символы")
    return text


def like_pattern(query: str) -> str:
    """Экранирует служебные символы LIKE и оборачивает запрос в %...%."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
