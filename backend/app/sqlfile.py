"""Вспомогательные функции для миграций, хранящих DDL в обычных .sql файлах.

Драйвер asyncpg не умеет выполнять несколько команд за один вызов, поэтому
SQL-файл делится на отдельные команды по строке "--;;".
"""
from __future__ import annotations

import re
from pathlib import Path


def split_statements(sql: str) -> list[str]:
    """Делит текст на команды по строкам "--;;" и убирает строки-комментарии."""
    result: list[str] = []
    for chunk in re.split(r"^--;;[ \t]*$", sql, flags=re.MULTILINE):
        lines = [ln for ln in chunk.splitlines() if not ln.lstrip().startswith("--")]
        statement = "\n".join(lines).strip()
        if statement:
            result.append(statement)
    return result


def run_sql_file(op, path: Path) -> None:
    for statement in split_statements(path.read_text(encoding="utf-8")):
        op.execute(statement)
