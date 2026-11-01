"""Регистрация, вход, выход, смена пароля и логина."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError

from .. import passwords, validators
from ..db import q_all, q_exec, q_one
from ..deps import DB, CurrentUser, CurrentUserAny, SettingsDep, client_ip
from ..errors import ApiError, conflict, too_many
from ..files import media_url
from ..services.common import audit, fav_sports_json
from ..tokens import create_access_token
from ..db import as_json

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    login: str
    password: str
    display_name: str | None = None

    @field_validator("login")
    @classmethod
    def _login(cls, v: str) -> str:
        return validators.validate_login(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validators.validate_password(v)

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validators.validate_display_name(v) if v and v.strip() else None


class LoginIn(BaseModel):
    login: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _new(cls, v: str) -> str:
        return validators.validate_password(v)


class ChangeLoginIn(BaseModel):
    password: str
    new_login: str

    @field_validator("new_login")
    @classmethod
    def _login(cls, v: str) -> str:
        return validators.validate_login(v)


async def load_me(db, user_id: int) -> dict[str, Any]:
    """Профиль текущего пользователя (с приватными полями)."""
    row = await q_one(
        db,
        f"SELECT u.id, u.login, u.display_name, u.avatar_path, u.role, u.can_review_reports, "
        f"u.must_change_password, u.created_at, {fav_sports_json('u')} AS favorite_sports "
        f"FROM users u WHERE u.id = :id",
        id=user_id,
    )
    assert row is not None
    row["avatar_url"] = media_url("avatars", row.pop("avatar_path"))
    row["favorite_sports"] = as_json(row["favorite_sports"], [])
    return row


async def _new_session(db, settings, user_id: int, user_agent: str | None) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=settings.access_token_days)
    row = await q_one(
        db,
        "INSERT INTO user_sessions (user_id, expires_at, user_agent) VALUES (:uid, :exp, :ua) RETURNING id",
        uid=user_id, exp=expires, ua=(user_agent or "")[:200] or None,
    )
    assert row is not None
    return create_access_token(settings.secret_key, user_id, row["id"], expires)


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, db: DB, settings: SettingsDep) -> dict[str, Any]:
    limiter = request.app.state.limiter
    key = f"register:{client_ip(request)}"
    if limiter.count(key, settings.register_window_seconds) >= settings.register_max_per_ip:
        raise too_many("Слишком много регистраций с этого адреса. Попробуйте позже.",
                       limiter.retry_after(key, settings.register_window_seconds))

    password_hash = await passwords.hash_password_async(body.password)
    display_name = body.display_name or body.login
    try:
        row = await q_one(
            db,
            "INSERT INTO users (login, password_hash, display_name) VALUES (:login, :ph, :dn) RETURNING id",
            login=body.login, ph=password_hash, dn=display_name[: validators.DISPLAY_NAME_MAX],
        )
    except IntegrityError as exc:
        await db.rollback()
        if "users_login_key" in str(exc.orig) or "unique" in str(exc.orig).lower():
            raise conflict("login_taken", "Этот логин уже занят") from None
        raise
    assert row is not None
    token = await _new_session(db, settings, row["id"], request.headers.get("user-agent"))
    await db.commit()
    limiter.hit(key, settings.register_window_seconds)
    return {"token": token, "user": await load_me(db, row["id"])}


@router.post("/login")
async def login(body: LoginIn, request: Request, db: DB, settings: SettingsDep) -> dict[str, Any]:
    limiter = request.app.state.limiter
    ip_key = f"login-ip:{client_ip(request)}"
    name_key = f"login-name:{body.login[:64]}"
    window = settings.login_window_seconds
    for key in (ip_key, name_key):
        if limiter.count(key, window) >= settings.login_max_attempts:
            raise too_many("Слишком много неудачных попыток входа. Подождите и попробуйте снова.",
                           limiter.retry_after(key, window))

    invalid = ApiError(401, "invalid_credentials", "Неверный логин или пароль")
    user = await q_one(
        db,
        "SELECT id, password_hash, is_active, deleted_at FROM users WHERE login = :login",
        login=validators.normalize_login(body.login),
    )
    if user is None or user["deleted_at"] is not None:
        await passwords.burn_dummy_verify(body.password)  # одинаковое время ответа
        limiter.hit(ip_key, window)
        limiter.hit(name_key, window)
        raise invalid
    if not await passwords.verify_password_async(user["password_hash"], body.password):
        limiter.hit(ip_key, window)
        limiter.hit(name_key, window)
        raise invalid
    if not user["is_active"]:
        raise ApiError(403, "account_disabled", "Аккаунт отключён администратором")

    if passwords.needs_rehash(user["password_hash"]):
        await q_exec(db, "UPDATE users SET password_hash = :ph WHERE id = :id",
                     ph=await passwords.hash_password_async(body.password), id=user["id"])
    token = await _new_session(db, settings, user["id"], request.headers.get("user-agent"))
    await q_exec(db, "UPDATE users SET last_seen_at = now() WHERE id = :id", id=user["id"])
    await db.commit()
    limiter.reset(name_key)
    return {"token": token, "user": await load_me(db, user["id"])}


@router.post("/logout", status_code=204)
async def logout(user: CurrentUserAny, db: DB) -> Response:
    await q_exec(db, "UPDATE user_sessions SET revoked_at = now() WHERE id = :sid", sid=user["sid"])
    await db.commit()
    return Response(status_code=204)


@router.get("/me")
async def me(user: CurrentUserAny, db: DB) -> dict[str, Any]:
    return await load_me(db, user["id"])


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: CurrentUserAny, db: DB) -> dict[str, Any]:
    row = await q_one(db, "SELECT password_hash FROM users WHERE id = :id", id=user["id"])
    assert row is not None
    if not await passwords.verify_password_async(row["password_hash"], body.current_password):
        raise ApiError(403, "wrong_password", "Текущий пароль указан неверно")
    if body.current_password == body.new_password:
        raise ApiError(422, "same_password", "Новый пароль должен отличаться от текущего")
    new_hash = await passwords.hash_password_async(body.new_password)
    await q_exec(
        db, "UPDATE users SET password_hash = :ph, must_change_password = FALSE WHERE id = :id",
        ph=new_hash, id=user["id"],
    )
    # остальные устройства выходят из аккаунта, текущая сессия сохраняется
    await q_exec(
        db, "UPDATE user_sessions SET revoked_at = now() "
            "WHERE user_id = :id AND id <> :sid AND revoked_at IS NULL",
        id=user["id"], sid=user["sid"],
    )
    await db.commit()
    return await load_me(db, user["id"])


@router.post("/change-login")
async def change_login(body: ChangeLoginIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    row = await q_one(db, "SELECT password_hash FROM users WHERE id = :id", id=user["id"])
    assert row is not None
    if not await passwords.verify_password_async(row["password_hash"], body.password):
        raise ApiError(403, "wrong_password", "Пароль указан неверно")
    try:
        await q_exec(db, "UPDATE users SET login = :login WHERE id = :id", login=body.new_login, id=user["id"])
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise conflict("login_taken", "Этот логин уже занят") from None
    return await load_me(db, user["id"])
