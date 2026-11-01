"""Профиль, поиск пользователей, аватар, удаление аккаунта, список видов спорта."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, field_validator

from .. import passwords, validators
from ..db import as_json, q_all, q_exec, q_one, q_val
from ..deps import DB, CurrentUser, SettingsDep, StoreDep
from ..errors import ApiError, conflict, forbidden, not_found, too_many
from ..files import media_url
from ..images import ImageLimits, process_image
from ..services.common import (audit, fav_sports_json, is_blocked_between, list_sports, public_user,
                               valid_sport_ids)
from .auth import load_me

logger = logging.getLogger("sportcourts.users")
router = APIRouter(tags=["users"])


class ProfileIn(BaseModel):
    display_name: str | None = None
    favorite_sport_ids: list[int] | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else validators.validate_display_name(v)

    @field_validator("favorite_sport_ids")
    @classmethod
    def _sports(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and len(set(v)) > 20:
            raise ValueError("Слишком много видов спорта")
        return v


class DeleteAccountIn(BaseModel):
    password: str


@router.get("/sports")
async def sports(user: CurrentUser, db: DB) -> dict[str, Any]:
    return {"items": await list_sports(db)}


@router.patch("/me")
async def update_profile(body: ProfileIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.display_name is not None:
        await q_exec(db, "UPDATE users SET display_name = :n WHERE id = :id", n=body.display_name, id=user["id"])
    if body.favorite_sport_ids is not None:
        ids = list(set(body.favorite_sport_ids))
        if ids and not await valid_sport_ids(db, ids):
            raise ApiError(422, "unknown_sport", "Выбран неизвестный вид спорта")
        await q_exec(db, "DELETE FROM user_favorite_sports WHERE user_id = :id", id=user["id"])
        if ids:
            await q_exec(
                db,
                "INSERT INTO user_favorite_sports (user_id, sport_id) "
                "SELECT :id, x FROM unnest(CAST(:ids AS integer[])) AS x",
                id=user["id"], ids=ids,
            )
    await db.commit()
    return await load_me(db, user["id"])


@router.put("/me/avatar")
async def set_avatar(user: CurrentUser, db: DB, settings: SettingsDep, store: StoreDep,
                     file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    limits = ImageLimits(settings.max_upload_mb * 1024 * 1024, settings.avatar_max_dimension,
                         settings.image_max_pixels, settings.jpeg_quality)
    jpeg = process_image(data, limits)  # ImageError -> 4xx с понятным текстом
    new_name = store.save("avatars", jpeg)
    try:
        old = await q_val(db, "SELECT avatar_path FROM users WHERE id = :id", id=user["id"])
        await q_exec(db, "UPDATE users SET avatar_path = :p WHERE id = :id", p=new_name, id=user["id"])
        await db.commit()
    except Exception:
        store.delete("avatars", new_name)  # не оставляем «осиротевший» файл
        raise
    store.delete("avatars", old)
    return await load_me(db, user["id"])


@router.delete("/me/avatar")
async def delete_avatar(user: CurrentUser, db: DB, store: StoreDep) -> dict[str, Any]:
    old = await q_val(db, "SELECT avatar_path FROM users WHERE id = :id", id=user["id"])
    await q_exec(db, "UPDATE users SET avatar_path = NULL WHERE id = :id", id=user["id"])
    await db.commit()
    store.delete("avatars", old)
    return await load_me(db, user["id"])


@router.post("/me/heartbeat", status_code=204)
async def heartbeat(user: CurrentUser) -> None:
    """Приложение вызывает это, пока открыто; обновление last_seen выполняет сама авторизация."""
    return None


@router.get("/users/search")
async def search_users(q: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    q = q.strip()
    if len(q) < 2:
        raise ApiError(422, "query_too_short", "Введите не меньше двух символов")
    rows = await q_all(
        db,
        f"""
        SELECT u.id, u.login, u.display_name, u.avatar_path, {fav_sports_json('u')} AS favorite_sports,
          CASE
            WHEN EXISTS (SELECT 1 FROM friendships f WHERE f.user_low_id = LEAST(u.id, :me)
                         AND f.user_high_id = GREATEST(u.id, :me)) THEN 'friend'
            WHEN EXISTS (SELECT 1 FROM friend_requests r WHERE r.status = 'pending'
                         AND r.sender_id = :me AND r.receiver_id = u.id) THEN 'request_sent'
            WHEN EXISTS (SELECT 1 FROM friend_requests r WHERE r.status = 'pending'
                         AND r.sender_id = u.id AND r.receiver_id = :me) THEN 'request_received'
            ELSE 'none' END AS relation
        FROM users u
        WHERE u.id <> :me AND u.is_active AND u.deleted_at IS NULL
          AND (u.login ILIKE :pat ESCAPE '\\' OR u.display_name ILIKE :pat ESCAPE '\\')
          AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE (b.blocker_id = :me AND b.blocked_id = u.id)
                          OR (b.blocker_id = u.id AND b.blocked_id = :me))
        ORDER BY (lower(u.login) = lower(:raw)) DESC, u.display_name, u.id
        LIMIT 20
        """,
        me=user["id"], pat=validators.like_pattern(q), raw=q,
    )
    items = []
    for r in rows:
        item = public_user({"id": r["id"], "login": r["login"], "display_name": r["display_name"],
                            "avatar_path": r["avatar_path"]})
        item["favorite_sports"] = as_json(r["favorite_sports"], [])
        item["relation"] = r["relation"]
        items.append(item)
    return {"items": items}


@router.get("/users/{user_id}")
async def get_user(user_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    row = await q_one(
        db,
        f"""
        SELECT u.id, u.login, u.display_name, u.avatar_path, {fav_sports_json('u')} AS favorite_sports,
               u.last_seen_at,
               EXISTS (SELECT 1 FROM friendships f WHERE f.user_low_id = LEAST(u.id, :me)
                       AND f.user_high_id = GREATEST(u.id, :me)) AS is_friend,
               EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id = :me AND b.blocked_id = u.id) AS blocked_by_me,
               (u.last_seen_at IS NOT NULL
                AND u.last_seen_at > now() - make_interval(secs => :online)) AS online
        FROM users u WHERE u.id = :id AND u.is_active AND u.deleted_at IS NULL
        """,
        id=user_id, me=user["id"], online=settings.online_timeout_seconds,
    )
    if row is None:
        raise not_found("Пользователь")
    if user_id != user["id"] and await is_blocked_between(db, user["id"], user_id) and not row["blocked_by_me"]:
        raise not_found("Пользователь")  # заблокировавший нас пользователь для нас «не существует»
    out = public_user({"id": row["id"], "login": row["login"], "display_name": row["display_name"],
                       "avatar_path": row["avatar_path"]})
    out["favorite_sports"] = as_json(row["favorite_sports"], [])
    out["is_friend"] = row["is_friend"]
    out["blocked_by_me"] = row["blocked_by_me"]
    out["is_self"] = user_id == user["id"]
    if row["is_friend"] or user_id == user["id"]:  # статус онлайн виден только друзьям
        out["online"] = row["online"]
        out["last_seen_at"] = row["last_seen_at"]
    return out


@router.delete("/me", status_code=204)
async def delete_account(body: DeleteAccountIn, user: CurrentUser, db: DB, store: StoreDep) -> None:
    """Удаление аккаунта: личные данные стираются, технические записи обезличиваются."""
    uid = user["id"]
    row = await q_one(db, "SELECT password_hash, avatar_path FROM users WHERE id = :id", id=uid)
    assert row is not None
    if not await passwords.verify_password_async(row["password_hash"], body.password):
        raise ApiError(403, "wrong_password", "Пароль указан неверно")
    if user["role"] == "admin":
        admins = await q_val(
            db, "SELECT count(*) FROM users WHERE role = 'admin' AND is_active AND deleted_at IS NULL")
        if admins <= 1:
            raise conflict("last_admin", "Нельзя удалить последнего администратора")

    # Фотографии на диске, которые станут ненужными
    pending_photos = await q_all(
        db,
        "SELECT photo_path FROM venue_submissions WHERE submitter_id = :id AND status = 'pending' AND photo_path IS NOT NULL "
        "UNION ALL SELECT photo_path FROM venue_change_proposals WHERE proposer_id = :id AND status = 'pending' "
        "AND photo_path IS NOT NULL",
        id=uid,
    )

    # Блокируем строки пользователя, чтобы параллельные операции не создавали новые связи
    await q_exec(db, "SELECT 1 FROM users WHERE id = :id FOR UPDATE", id=uid)
    # открытые игры организатора отменяются, из чужих игр пользователь выходит
    await q_exec(db, "UPDATE games SET status = 'cancelled', closed_at = now() "
                     "WHERE organizer_id = :id AND status = 'open'", id=uid)
    await q_exec(db, "DELETE FROM game_participants WHERE user_id = :id AND game_id IN "
                     "(SELECT id FROM games WHERE status = 'open')", id=uid)
    await q_exec(db, "UPDATE presence_checkins SET ended_at = now(), end_reason = 'manual' "
                     "WHERE user_id = :id AND ended_at IS NULL", id=uid)
    # личные данные и переписка
    for sql in (
        "DELETE FROM messages WHERE sender_id = :id OR recipient_id = :id",
        "DELETE FROM notifications WHERE user_id = :id",
        "DELETE FROM friend_requests WHERE sender_id = :id OR receiver_id = :id",
        "DELETE FROM friendships WHERE user_low_id = :id OR user_high_id = :id",
        "DELETE FROM user_blocks WHERE blocker_id = :id OR blocked_id = :id",
        "DELETE FROM user_favorite_sports WHERE user_id = :id",
        "DELETE FROM user_sessions WHERE user_id = :id",
        "DELETE FROM moderator_requests WHERE user_id = :id",
        "DELETE FROM venue_submissions WHERE submitter_id = :id AND status = 'pending'",
        "DELETE FROM venue_change_proposals WHERE proposer_id = :id AND status = 'pending'",
    ):
        await q_exec(db, sql, id=uid)
    # жалобы, написанные пользователем, остаются, но без описания (там мог быть личный текст)
    await q_exec(db, "UPDATE reports SET description = NULL WHERE reporter_id = :id", id=uid)
    # сама запись остаётся обезличенной ради целостности истории (игры, заявки, отчёты)
    await q_exec(
        db,
        "UPDATE users SET login = :ghost, display_name = 'Удалённый пользователь', password_hash = :bad, "
        "avatar_path = NULL, role = 'user', can_review_reports = FALSE, is_active = FALSE, "
        "must_change_password = FALSE, deleted_at = now(), last_seen_at = NULL WHERE id = :id",
        ghost=f"deleted:{uid}", bad=passwords.UNUSABLE_HASH, id=uid,
    )
    await audit(db, None, "account_deleted", "user", uid)
    await db.commit()

    store.delete("avatars", row["avatar_path"])
    for p in pending_photos:
        store.delete("venues", p["photo_path"])
    logger.info("Аккаунт %s удалён и обезличен", uid)
