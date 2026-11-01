"""Режим «строгих параметров» для запуска тестов через psycopg (только для разработки).

Рабочий драйвер сервера — asyncpg. Он, в отличие от psycopg, не умеет угадывать тип параметра,
если контекст его не определяет (например, `:x IS NULL`): возникает ошибка
«could not determine data type of parameter». Этот модуль заставляет psycopg отправлять
все параметры без типа (OID 0) — так тесты ловят такие ошибки и на psycopg.

Включается переменной окружения SC_STRICT_PARAMS=1 и нужен только если вы запускаете тесты с
драйвером postgresql+psycopg. С asyncpg (как в README) он не используется.
"""
from __future__ import annotations

import datetime as dt
import decimal

from psycopg.adapt import Dumper
from psycopg.pq import Format
from psycopg.adapt import AdaptersMap
from psycopg import adapters


class _UntypedDumper(Dumper):
    format = Format.TEXT
    oid = 0

    def dump(self, obj):  # type: ignore[override]
        if isinstance(obj, bool):
            return b"t" if obj else b"f"
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            return obj.isoformat().encode()
        if isinstance(obj, (list, tuple)):
            return ("{" + ",".join(_array_item(x) for x in obj) + "}").encode()
        return str(obj).encode()


def _array_item(x) -> str:
    if x is None:
        return "NULL"
    if isinstance(x, (int, float, decimal.Decimal)):
        return str(x)
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


for _type in (int, float, str, bool, dt.datetime, dt.date, list, decimal.Decimal):
    adapters.register_dumper(_type, _UntypedDumper)
