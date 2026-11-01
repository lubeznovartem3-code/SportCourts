"""Единый формат ошибок API.

Любая ошибка возвращается как JSON:
    {"error": {"code": "login_taken", "message": "Этот логин уже занят", "details": ...}}
Поле code — стабильный машинный код, message — текст для пользователя на русском.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .images import ImageError

logger = logging.getLogger("sportcourts.api")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


# Часто используемые ошибки -----------------------------------------------------
def not_found(what: str = "Объект") -> ApiError:
    return ApiError(404, "not_found", f"{what} не найден")


def forbidden(message: str = "Недостаточно прав", code: str = "forbidden") -> ApiError:
    return ApiError(403, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def unprocessable(code: str, message: str) -> ApiError:
    return ApiError(422, code, message)


def too_many(message: str, retry_after: int) -> ApiError:
    return ApiError(
        429, "rate_limited", message, details={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


def _json(status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, details), headers=headers)


_VALIDATION_MESSAGES = {
    "missing": "обязательное поле не указано",
    "string_too_short": "слишком короткое значение",
    "string_too_long": "слишком длинное значение",
    "greater_than_equal": "значение слишком мало",
    "less_than_equal": "значение слишком велико",
    "greater_than": "значение слишком мало",
    "less_than": "значение слишком велико",
    "int_parsing": "нужно целое число",
    "float_parsing": "нужно число",
    "bool_parsing": "нужно логическое значение",
    "literal_error": "недопустимое значение",
    "too_short": "слишком мало элементов",
    "too_long": "слишком много элементов",
    "datetime_from_date_parsing": "некорректная дата",
    "datetime_parsing": "некорректная дата и время",
    "timezone_aware": "укажите время вместе с часовым поясом",
    "json_invalid": "некорректный JSON",
}


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        msg = str(err.get("msg", ""))
        if msg.startswith("Value error, "):  # наши валидаторы бросают ValueError с русским текстом
            text = msg[len("Value error, "):]
        else:
            text = _VALIDATION_MESSAGES.get(str(err.get("type")), "некорректное значение")
        details.append({"field": ".".join(loc), "message": text})
    return details


def is_db_unavailable(exc: BaseException) -> bool:
    """True, если исключение означает «база данных недоступна» (а не ошибку запроса)."""
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _json(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(ImageError)
    async def _image_error(_: Request, exc: ImageError) -> JSONResponse:
        return _json(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = _validation_details(exc)
        first = details[0] if details else {"field": "", "message": "некорректные данные"}
        field = f"«{first['field']}»: " if first["field"] else ""
        return _json(422, "validation_error", f"Проверьте данные: {field}{first['message']}", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapping = {
            401: ("not_authenticated", "Требуется вход в аккаунт"),
            403: ("forbidden", "Недостаточно прав"),
            404: ("not_found", "Не найдено"),
            405: ("method_not_allowed", "Метод не поддерживается"),
            413: ("payload_too_large", "Слишком большой запрос"),
        }
        code, default = mapping.get(exc.status_code, ("http_error", "Ошибка запроса"))
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code not in mapping else default
        return _json(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _db_down(_: Request, exc: Exception) -> JSONResponse:
        logger.error("База данных недоступна: %s", type(exc).__name__)
        return _json(503, "database_unavailable", "Сервис временно недоступен: нет связи с базой данных. Попробуйте позже.")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        if is_db_unavailable(exc):
            logger.error("Нет связи с базой данных: %s", type(exc).__name__)
            return _json(503, "database_unavailable", "Сервис временно недоступен: нет связи с базой данных. Попробуйте позже.")
        logger.exception("Необработанная ошибка API")
        return _json(500, "internal_error", "Внутренняя ошибка сервера. Попробуйте позже.")
