"""Зависимости FastAPI: настройки, авторизация, роли, ограничители частоты."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .db import get_db, q_one, q_exec
from .errors import ApiError, forbidden
from .files import FileStore
from .tokens import decode_access_token

DB = Annotated[AsyncSession, Depends(get_db)]

LAST_SEEN_THROTTLE_SECONDS = 20


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> FileStore:
    return request.app.state.store


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
StoreDep = Annotated[FileStore, Depends(get_store)]


def client_ip(request: Request) -> str:
    """IP клиента. Заголовки прокси учитывает сам uvicorn, и только от доверенных адресов
    (TRUSTED_PROXY_IPS); произвольным заголовкам клиента мы здесь не доверяем."""
    return request.client.host if request.client else "unknown"


_AUTH_SQL = """
SELECT u.id, u.login, u.display_name, u.avatar_path, u.role, u.can_review_reports,
       u.must_change_password, s.id AS sid
FROM user_sessions s
JOIN users u ON u.id = s.user_id
WHERE s.id = :sid AND s.user_id = :uid
  AND s.revoked_at IS NULL AND s.expires_at > now()
  AND u.is_active AND u.deleted_at IS NULL
"""


async def _authenticate(request: Request, db: AsyncSession) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "not_authenticated", "Требуется вход в аккаунт",
                       headers={"WWW-Authenticate": "Bearer"})
    settings: Settings = request.app.state.settings
    payload = decode_access_token(settings.secret_key, token.strip())
    if payload is None:
        raise ApiError(401, "invalid_token", "Сессия недействительна. Войдите заново.",
                       headers={"WWW-Authenticate": "Bearer"})
    user = await q_one(db, _AUTH_SQL, sid=payload["sid"], uid=payload["user_id"])
    if user is None:
        raise ApiError(401, "invalid_token", "Сессия недействительна. Войдите заново.",
                       headers={"WWW-Authenticate": "Bearer"})
    # «Онлайн» определяется по недавней активности; пишем не чаще раза в 20 секунд.
    changed = await q_exec(
        db,
        "UPDATE users SET last_seen_at = now() WHERE id = :uid "
        "AND (last_seen_at IS NULL OR last_seen_at < now() - make_interval(secs => :secs))",
        uid=user["id"], secs=LAST_SEEN_THROTTLE_SECONDS,
    )
    if changed:
        await db.commit()
    return user


async def current_user_any(request: Request, db: DB) -> dict[str, Any]:
    """Пользователь без проверки обязательной смены пароля (нужен только для смены пароля)."""
    return await _authenticate(request, db)


async def current_user(user: Annotated[dict[str, Any], Depends(current_user_any)]) -> dict[str, Any]:
    if user["must_change_password"]:
        raise ApiError(403, "password_change_required", "Необходимо сменить временный пароль")
    return user


async def require_moderator(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    if user["role"] not in ("moderator", "admin"):
        raise forbidden("Доступно только модераторам")
    return user


async def require_admin(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    if user["role"] != "admin":
        raise forbidden("Доступно только администратору")
    return user


async def require_report_reviewer(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    if user["role"] == "admin" or (user["role"] == "moderator" and user["can_review_reports"]):
        return user
    raise forbidden("Рассматривать жалобы может только администратор")


CurrentUserAny = Annotated[dict[str, Any], Depends(current_user_any)]
CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
Moderator = Annotated[dict[str, Any], Depends(require_moderator)]
Admin = Annotated[dict[str, Any], Depends(require_admin)]
ReportReviewer = Annotated[dict[str, Any], Depends(require_report_reviewer)]
