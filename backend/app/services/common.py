"""Общие операции: уведомления, аудит, блокировки, сериализация пользователей и площадок."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import as_json, q_all, q_exec, q_one, q_val
from ..files import media_url

logger = logging.getLogger("sportcourts.audit")

# SQL-фрагмент: публичные данные пользователя как JSON (alias — имя таблицы/псевдонима users)
def user_json(alias: str) -> str:
    return (
        f"json_build_object('id', {alias}.id, 'login', {alias}.login, "
        f"'display_name', {alias}.display_name, 'avatar_path', {alias}.avatar_path)"
    )


def fav_sports_json(alias: str) -> str:
    return (
        "coalesce((SELECT json_agg(json_build_object('id', s.id, 'code', s.code, 'name', s.name) "
        "ORDER BY s.sort_order, s.id) FROM user_favorite_sports f JOIN sports s ON s.id = f.sport_id "
        f"WHERE f.user_id = {alias}.id), '[]'::json)"
    )


def sports_json_for(table: str, key: str, alias_id: str) -> str:
    """JSON-массив видов спорта для площадки/заявки/предложения."""
    return (
        "coalesce((SELECT json_agg(json_build_object('id', sp.id, 'code', sp.code, 'name', sp.name) "
        f"ORDER BY sp.sort_order, sp.id) FROM {table} t JOIN sports sp ON sp.id = t.sport_id "
        f"WHERE t.{key} = {alias_id}), '[]'::json)"
    )


def public_user(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """Преобразует {'avatar_path': ...} в {'avatar_url': ...}."""
    if obj is None:
        return None
    obj = as_json(obj)
    out = {k: v for k, v in obj.items() if k != "avatar_path"}
    out["avatar_url"] = media_url("avatars", obj.get("avatar_path"))
    return out


def venue_photo_url(path: str | None) -> str | None:
    return media_url("venues", path)


# ----------------------------------------------------------------------- уведомления
async def notify(
    db: AsyncSession, user_id: int, type_: str, title: str, body: str | None = None, ref_id: int | None = None
) -> None:
    await q_exec(
        db,
        "INSERT INTO notifications (user_id, type, title, body, ref_id) "
        "VALUES (:uid, :type, :title, :body, :ref)",
        uid=user_id, type=type_, title=title, body=body, ref=ref_id,
    )


# ----------------------------------------------------------------------- аудит
async def audit(
    db: AsyncSession, actor_id: int | None, action: str, target_type: str | None = None,
    target_id: int | None = None, details: str | None = None,
) -> None:
    await q_exec(
        db,
        "INSERT INTO audit_log (actor_id, action, target_type, target_id, details) "
        "VALUES (:actor, :action, :tt, :tid, :details)",
        actor=actor_id, action=action, tt=target_type, tid=target_id, details=details,
    )
    logger.info("AUDIT actor=%s action=%s target=%s:%s", actor_id, action, target_type, target_id)


# ----------------------------------------------------------------------- блокировки и дружба
async def is_blocked_between(db: AsyncSession, a: int, b: int) -> bool:
    return bool(await q_val(
        db,
        "SELECT EXISTS (SELECT 1 FROM user_blocks WHERE (blocker_id = :a AND blocked_id = :b) "
        "OR (blocker_id = :b AND blocked_id = :a))",
        a=a, b=b,
    ))


async def are_friends(db: AsyncSession, a: int, b: int) -> bool:
    low, high = (a, b) if a < b else (b, a)
    return bool(await q_val(
        db,
        "SELECT EXISTS (SELECT 1 FROM friendships WHERE user_low_id = :low AND user_high_id = :high)",
        low=low, high=high,
    ))


async def get_active_user(db: AsyncSession, user_id: int) -> dict[str, Any] | None:
    return await q_one(
        db,
        "SELECT id, login, display_name, avatar_path, role FROM users "
        "WHERE id = :id AND is_active AND deleted_at IS NULL",
        id=user_id,
    )


async def list_sports(db: AsyncSession, include_inactive: bool = False) -> list[dict[str, Any]]:
    return await q_all(
        db,
        "SELECT id, code, name, is_active FROM sports "
        "WHERE (is_active OR CAST(:all AS boolean)) ORDER BY sort_order, id",
        all=include_inactive,
    )


async def valid_sport_ids(db: AsyncSession, ids: list[int]) -> bool:
    if not ids:
        return False
    count = await q_val(
        db, "SELECT count(*) FROM sports WHERE is_active AND id = ANY(CAST(:ids AS integer[]))", ids=list(set(ids))
    )
    return count == len(set(ids))
