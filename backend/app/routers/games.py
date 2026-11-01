"""Открытые игры и сбор состава."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from .. import validators
from ..db import as_json, q_all, q_exec, q_one, q_val
from ..deps import DB, CurrentUser, SettingsDep
from ..errors import ApiError, conflict, forbidden, not_found
from ..services.common import (are_friends, is_blocked_between, public_user, sports_json_for, user_json)

router = APIRouter(tags=["games"])


class GameIn(BaseModel):
    venue_id: int
    title: str
    starts_at: datetime
    max_players: int = Field(ge=2, le=100)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        text = validators.clean_text(v, 80, "Название")
        if not text:
            raise ValueError("Название не может быть пустым")
        return text

    @field_validator("starts_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Укажите время вместе с часовым поясом")
        return v


class InviteIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=20)


GAME_SELECT = f"""
SELECT g.id, g.title, g.starts_at, g.max_players, g.status, g.created_at, g.closed_at,
       g.venue_id, v.name AS venue_name, v.address AS venue_address,
       {sports_json_for('venue_sports', 'venue_id', 'v.id')} AS venue_sports,
       {user_json('o')} AS organizer,
       (SELECT count(*) FROM game_participants gp WHERE gp.game_id = g.id) AS participants_count,
       EXISTS (SELECT 1 FROM game_participants gp WHERE gp.game_id = g.id AND gp.user_id = :me) AS joined
FROM games g
JOIN venues v ON v.id = g.venue_id
JOIN users o ON o.id = g.organizer_id
"""


def serialize_game(r: dict[str, Any], me: int) -> dict[str, Any]:
    organizer = public_user(r["organizer"])
    return {
        "id": r["id"], "title": r["title"], "starts_at": r["starts_at"], "max_players": r["max_players"],
        "status": r["status"], "created_at": r["created_at"], "closed_at": r["closed_at"],
        "venue": {"id": r["venue_id"], "name": r["venue_name"], "address": r["venue_address"],
                  "sports": as_json(r["venue_sports"], [])},
        "organizer": organizer,
        "participants_count": r["participants_count"],
        "free_slots": max(0, r["max_players"] - r["participants_count"]),
        "joined": bool(r["joined"]),
        "is_organizer": organizer["id"] == me,
    }


async def load_game(db, game_id: int, me: int, settings=None) -> dict[str, Any]:
    row = await q_one(db, GAME_SELECT + " WHERE g.id = :id", id=game_id, me=me)
    if row is None:
        raise not_found("Игра")
    game = serialize_game(row, me)
    parts = await q_all(
        db,
        f"""SELECT {user_json('u')} AS user, gp.joined_at, (gp.user_id = g.organizer_id) AS is_organizer
            FROM game_participants gp JOIN games g ON g.id = gp.game_id JOIN users u ON u.id = gp.user_id
            WHERE gp.game_id = :id ORDER BY is_organizer DESC, gp.joined_at, u.id""",
        id=game_id,
    )
    game["participants"] = [
        {"user": public_user(p["user"]), "joined_at": p["joined_at"], "is_organizer": p["is_organizer"]}
        for p in parts
    ]
    return game


def _active_filter() -> str:
    return "g.status = 'open' AND g.starts_at > now() - make_interval(hours => :grace)"


@router.get("/games")
async def list_games(
    user: CurrentUser, db: DB, settings: SettingsDep,
    scope: Literal["open", "mine", "history"] = "open",
    venue_id: int | None = None,
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """open — активные игры; mine — где я участвую (активные); history — завершённые/отменённые/прошедшие."""
    if scope == "open":
        where = f"{_active_filter()} AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE " \
                "(b.blocker_id = :me AND b.blocked_id = g.organizer_id) OR (b.blocker_id = g.organizer_id AND b.blocked_id = :me))"
        order = "g.starts_at ASC, g.id"
    elif scope == "mine":
        where = f"{_active_filter()} AND EXISTS (SELECT 1 FROM game_participants gp WHERE gp.game_id = g.id AND gp.user_id = :me)"
        order = "g.starts_at ASC, g.id"
    else:
        where = ("NOT (g.status = 'open' AND g.starts_at > now() - make_interval(hours => :grace)) AND "
                 "EXISTS (SELECT 1 FROM game_participants gp WHERE gp.game_id = g.id AND gp.user_id = :me)")
        order = "g.starts_at DESC, g.id DESC"
    rows = await q_all(
        db,
        GAME_SELECT + f" WHERE {where} AND (CAST(:venue AS bigint) IS NULL OR g.venue_id = CAST(:venue AS bigint)) "
                      f"ORDER BY {order} LIMIT :limit OFFSET :offset",
        me=user["id"], grace=settings.game_list_grace_hours, venue=venue_id, limit=limit, offset=offset,
    )
    return {"items": [serialize_game(r, user["id"]) for r in rows], "limit": limit, "offset": offset}


@router.post("/games", status_code=201)
async def create_game(body: GameIn, user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if body.starts_at < now - timedelta(minutes=10):
        raise ApiError(422, "start_in_past", "Время начала игры уже прошло")
    if body.starts_at > now + timedelta(days=180):
        raise ApiError(422, "start_too_far", "Игру можно создать не дальше чем на полгода вперёд")
    if not await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id AND status = 'active')", id=body.venue_id):
        raise not_found("Площадка")
    await q_exec(db, "SELECT pg_advisory_xact_lock(CAST(:k AS bigint))", k=user["id"])
    open_games = await q_val(
        db, f"SELECT count(*) FROM games g WHERE g.organizer_id = :u AND {_active_filter()}",
        u=user["id"], grace=settings.game_list_grace_hours,
    )
    if open_games >= settings.max_open_games_per_user:
        raise ApiError(429, "too_many_games", "У вас уже слишком много активных игр. Завершите или отмените лишние.")
    game = await q_one(
        db,
        "INSERT INTO games (venue_id, organizer_id, title, starts_at, max_players) "
        "VALUES (:v, :u, :t, :s, :m) RETURNING id",
        v=body.venue_id, u=user["id"], t=body.title, s=body.starts_at, m=body.max_players,
    )
    assert game is not None
    await q_exec(db, "INSERT INTO game_participants (game_id, user_id) VALUES (:g, :u)", g=game["id"], u=user["id"])
    await db.commit()
    return await load_game(db, game["id"], user["id"])


@router.get("/games/{game_id}")
async def get_game(game_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    return await load_game(db, game_id, user["id"])


@router.post("/games/{game_id}/join")
async def join_game(game_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    """Присоединение. Строка игры блокируется, поэтому при одновременных запросах мест не станет больше лимита."""
    game = await q_one(
        db, "SELECT id, organizer_id, status, max_players, starts_at FROM games WHERE id = :id FOR UPDATE", id=game_id)
    if game is None:
        raise not_found("Игра")
    if game["status"] != "open":
        raise conflict("game_closed", "Игра уже закрыта")
    if game["starts_at"] < datetime.now(timezone.utc) - timedelta(hours=settings.game_list_grace_hours):
        raise conflict("game_over", "Время игры уже прошло")
    if await is_blocked_between(db, user["id"], game["organizer_id"]):
        raise forbidden("Присоединиться к этой игре нельзя", "blocked")
    if await q_val(db, "SELECT EXISTS (SELECT 1 FROM game_participants WHERE game_id = :g AND user_id = :u)",
                   g=game_id, u=user["id"]):
        raise conflict("already_joined", "Вы уже участвуете в этой игре")
    count = await q_val(db, "SELECT count(*) FROM game_participants WHERE game_id = :g", g=game_id)
    if count >= game["max_players"]:
        raise conflict("game_full", "Свободных мест не осталось")
    try:
        await q_exec(db, "INSERT INTO game_participants (game_id, user_id) VALUES (:g, :u)", g=game_id, u=user["id"])
        await db.commit()
    except IntegrityError as exc:  # страховка: триггер БД тоже не даст превысить лимит
        await db.rollback()
        if "game_full" in str(exc.orig):
            raise conflict("game_full", "Свободных мест не осталось") from None
        raise conflict("already_joined", "Вы уже участвуете в этой игре") from None
    return await load_game(db, game_id, user["id"])


@router.post("/games/{game_id}/leave")
async def leave_game(game_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    game = await q_one(db, "SELECT id, organizer_id, status FROM games WHERE id = :id FOR UPDATE", id=game_id)
    if game is None:
        raise not_found("Игра")
    if game["organizer_id"] == user["id"]:
        raise conflict("organizer_cannot_leave", "Организатор не может выйти из игры. Отмените её или завершите.")
    if game["status"] != "open":
        raise conflict("game_closed", "Игра уже закрыта")
    removed = await q_exec(db, "DELETE FROM game_participants WHERE game_id = :g AND user_id = :u",
                           g=game_id, u=user["id"])
    if not removed:
        raise conflict("not_participant", "Вы не участвуете в этой игре")
    await db.commit()
    return await load_game(db, game_id, user["id"])


async def _close(game_id: int, user: dict[str, Any], db, new_status: str) -> dict[str, Any]:
    game = await q_one(db, "SELECT id, organizer_id, status FROM games WHERE id = :id FOR UPDATE", id=game_id)
    if game is None:
        raise not_found("Игра")
    if game["organizer_id"] != user["id"]:
        raise forbidden("Только организатор может это сделать", "not_organizer")
    if game["status"] != "open":
        raise conflict("game_closed", "Игра уже закрыта")
    await q_exec(db, "UPDATE games SET status = :s, closed_at = now() WHERE id = :id", s=new_status, id=game_id)
    await db.commit()
    return await load_game(db, game_id, user["id"])


@router.post("/games/{game_id}/cancel")
async def cancel_game(game_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    return await _close(game_id, user, db, "cancelled")


@router.post("/games/{game_id}/finish")
async def finish_game(game_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    return await _close(game_id, user, db, "finished")


@router.post("/games/{game_id}/invite")
async def invite_friends(game_id: int, body: InviteIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Отправляет друзьям личное сообщение с приглашением в игру (только друзьям, без блокировок)."""
    game = await q_one(
        db,
        "SELECT g.id, g.title, g.starts_at, g.status, g.organizer_id, v.name AS venue_name "
        "FROM games g JOIN venues v ON v.id = g.venue_id WHERE g.id = :id",
        id=game_id,
    )
    if game is None:
        raise not_found("Игра")
    if game["status"] != "open":
        raise conflict("game_closed", "Игра уже закрыта")
    if not await q_val(db, "SELECT EXISTS (SELECT 1 FROM game_participants WHERE game_id = :g AND user_id = :u)",
                       g=game_id, u=user["id"]):
        raise forbidden("Приглашать могут только участники игры", "not_participant")
    sent, skipped = [], []
    for uid in dict.fromkeys(body.user_ids):
        if uid == user["id"] or not await are_friends(db, user["id"], uid) \
                or await is_blocked_between(db, user["id"], uid):
            skipped.append(uid)
            continue
        text = (f"Приглашаю на игру «{game['title']}» — {game['venue_name']}, "
                f"{game['starts_at'].astimezone(timezone(timedelta(hours=3))).strftime('%d.%m %H:%M')} (МСК).")
        await q_exec(db, "INSERT INTO messages (sender_id, recipient_id, body) VALUES (:s, :r, :b)",
                     s=user["id"], r=uid, b=text[:2000])
        sent.append(uid)
    await db.commit()
    return {"sent": sent, "skipped": skipped}
