"""Друзья, блокировки, жалобы, личные сообщения, уведомления."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError

from .. import validators
from ..db import as_json, q_all, q_exec, q_one, q_val
from ..deps import DB, CurrentUser, SettingsDep
from ..errors import ApiError, conflict, forbidden, not_found, too_many
from ..services.common import (are_friends, get_active_user, is_blocked_between, notify, public_user, user_json)

router = APIRouter(tags=["social"])


def _ordered(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


# ============================================================================ друзья
class FriendRequestIn(BaseModel):
    user_id: int


@router.get("/friends")
async def list_friends(user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    rows = await q_all(
        db,
        f"""
        SELECT {user_json('u')} AS user, u.last_seen_at,
               (u.last_seen_at IS NOT NULL AND u.last_seen_at > now() - make_interval(secs => :online)) AS online,
               (SELECT v.name FROM presence_checkins p JOIN venues v ON v.id = p.venue_id
                 WHERE p.user_id = u.id AND p.ended_at IS NULL AND p.expires_at > now() LIMIT 1) AS at_venue,
               (SELECT g.title FROM games g WHERE g.organizer_id = u.id AND g.status = 'open'
                 AND g.starts_at > now() - make_interval(hours => :grace) ORDER BY g.starts_at LIMIT 1) AS organizing_game,
               (SELECT count(*) FROM messages m WHERE m.sender_id = u.id AND m.recipient_id = :me
                 AND m.read_at IS NULL) AS unread
        FROM friendships f
        JOIN users u ON u.id = CASE WHEN f.user_low_id = :me THEN f.user_high_id ELSE f.user_low_id END
        WHERE (f.user_low_id = :me OR f.user_high_id = :me) AND u.is_active AND u.deleted_at IS NULL
        ORDER BY online DESC, lower(u.display_name), u.id
        """,
        me=user["id"], online=settings.online_timeout_seconds, grace=settings.game_list_grace_hours,
    )
    items = []
    for r in rows:
        item = public_user(r["user"])
        item.update({
            "online": r["online"], "last_seen_at": r["last_seen_at"], "unread_messages": r["unread"],
            "activity": (f"Собирает состав: {r['organizing_game']}" if r["organizing_game"]
                         else f"На площадке: {r['at_venue']}" if r["at_venue"] else None),
        })
        items.append(item)
    return {"items": items}


@router.delete("/friends/{friend_id}", status_code=204)
async def remove_friend(friend_id: int, user: CurrentUser, db: DB) -> Response:
    low, high = _ordered(user["id"], friend_id)
    removed = await q_exec(db, "DELETE FROM friendships WHERE user_low_id = :l AND user_high_id = :h", l=low, h=high)
    if not removed:
        raise not_found("Друг")
    await db.commit()
    return Response(status_code=204)


async def _create_friendship(db, a: int, b: int) -> None:
    low, high = _ordered(a, b)
    await q_exec(db, "INSERT INTO friendships (user_low_id, user_high_id) VALUES (:l, :h) ON CONFLICT DO NOTHING",
                 l=low, h=high)


@router.post("/friend-requests", status_code=201)
async def send_friend_request(body: FriendRequestIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    me, other = user["id"], body.user_id
    if other == me:
        raise ApiError(422, "self_request", "Нельзя добавить в друзья самого себя")
    target = await get_active_user(db, other)
    if target is None:
        raise not_found("Пользователь")
    if await is_blocked_between(db, me, other):
        raise forbidden("Действие недоступно из-за блокировки", "blocked")
    if await are_friends(db, me, other):
        raise conflict("already_friends", "Вы уже друзья")
    await q_exec(db, "SELECT pg_advisory_xact_lock(CAST(:k AS bigint))", k=_ordered(me, other)[0] * 1_000_003 + _ordered(me, other)[1])
    reverse = await q_one(
        db, "SELECT id FROM friend_requests WHERE sender_id = :o AND receiver_id = :me AND status = 'pending' FOR UPDATE",
        o=other, me=me)
    if reverse is not None:  # встречный запрос уже есть — просто принимаем его
        await q_exec(db, "UPDATE friend_requests SET status = 'accepted', responded_at = now() WHERE id = :id", id=reverse["id"])
        await _create_friendship(db, me, other)
        await notify(db, other, "friend_accepted", "Запрос в друзья принят",
                     f"{user['display_name']} теперь в списке ваших друзей.", me)
        await db.commit()
        return {"status": "accepted", "request_id": reverse["id"]}
    try:
        row = await q_one(
            db, "INSERT INTO friend_requests (sender_id, receiver_id) VALUES (:s, :r) RETURNING id",
            s=me, r=other)
    except IntegrityError:
        await db.rollback()
        raise conflict("request_exists", "Запрос уже отправлен") from None
    assert row is not None
    await notify(db, other, "friend_request", "Новый запрос в друзья",
                 f"{user['display_name']} (@{user['login']}) хочет добавить вас в друзья.", row["id"])
    await db.commit()
    return {"status": "pending", "request_id": row["id"]}


@router.get("/friend-requests")
async def list_friend_requests(user: CurrentUser, db: DB,
                               direction: Literal["incoming", "outgoing"] = "incoming") -> dict[str, Any]:
    incoming = direction == "incoming"
    rows = await q_all(
        db,
        f"""SELECT r.id, r.created_at, {user_json('u')} AS user
            FROM friend_requests r JOIN users u ON u.id = {'r.sender_id' if incoming else 'r.receiver_id'}
            WHERE {'r.receiver_id' if incoming else 'r.sender_id'} = :me AND r.status = 'pending'
              AND u.is_active AND u.deleted_at IS NULL
            ORDER BY r.id DESC LIMIT 100""",
        me=user["id"],
    )
    return {"items": [{"id": r["id"], "created_at": r["created_at"], "user": public_user(r["user"])} for r in rows]}


async def _load_pending(db, request_id: int) -> dict[str, Any]:
    row = await q_one(db, "SELECT * FROM friend_requests WHERE id = :id FOR UPDATE", id=request_id)
    if row is None:
        raise not_found("Запрос")
    if row["status"] != "pending":
        raise conflict("already_handled", "Запрос уже обработан")
    return row


@router.post("/friend-requests/{request_id}/accept")
async def accept_request(request_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    r = await _load_pending(db, request_id)
    if r["receiver_id"] != user["id"]:
        raise forbidden("Это не ваш запрос")
    if await is_blocked_between(db, r["sender_id"], user["id"]):
        raise forbidden("Действие недоступно из-за блокировки", "blocked")
    await q_exec(db, "UPDATE friend_requests SET status = 'accepted', responded_at = now() WHERE id = :id", id=request_id)
    await _create_friendship(db, r["sender_id"], user["id"])
    await notify(db, r["sender_id"], "friend_accepted", "Запрос в друзья принят",
                 f"{user['display_name']} принял(а) ваш запрос.", user["id"])
    await db.commit()
    return {"status": "accepted"}


@router.post("/friend-requests/{request_id}/decline")
async def decline_request(request_id: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    r = await _load_pending(db, request_id)
    if r["receiver_id"] != user["id"]:
        raise forbidden("Это не ваш запрос")
    await q_exec(db, "UPDATE friend_requests SET status = 'declined', responded_at = now() WHERE id = :id", id=request_id)
    await db.commit()
    return {"status": "declined"}


@router.delete("/friend-requests/{request_id}", status_code=204)
async def cancel_request(request_id: int, user: CurrentUser, db: DB) -> Response:
    r = await _load_pending(db, request_id)
    if r["sender_id"] != user["id"]:
        raise forbidden("Это не ваш запрос")
    await q_exec(db, "UPDATE friend_requests SET status = 'cancelled', responded_at = now() WHERE id = :id", id=request_id)
    await db.commit()
    return Response(status_code=204)


# ============================================================================ блокировки
@router.get("/blocks")
async def list_blocks(user: CurrentUser, db: DB) -> dict[str, Any]:
    rows = await q_all(
        db,
        f"SELECT {user_json('u')} AS user, b.created_at FROM user_blocks b JOIN users u ON u.id = b.blocked_id "
        "WHERE b.blocker_id = :me ORDER BY b.created_at DESC", me=user["id"])
    return {"items": [{"user": public_user(r["user"]), "created_at": r["created_at"]} for r in rows]}


@router.post("/blocks/{target_id}", status_code=204)
async def block_user(target_id: int, user: CurrentUser, db: DB) -> Response:
    if target_id == user["id"]:
        raise ApiError(422, "self_block", "Нельзя заблокировать самого себя")
    if await get_active_user(db, target_id) is None:
        raise not_found("Пользователь")
    me = user["id"]
    await q_exec(db, "INSERT INTO user_blocks (blocker_id, blocked_id) VALUES (:a, :b) ON CONFLICT DO NOTHING",
                 a=me, b=target_id)
    low, high = _ordered(me, target_id)
    await q_exec(db, "DELETE FROM friendships WHERE user_low_id = :l AND user_high_id = :h", l=low, h=high)
    await q_exec(db, "UPDATE friend_requests SET status = 'cancelled', responded_at = now() WHERE status = 'pending' "
                     "AND ((sender_id = :a AND receiver_id = :b) OR (sender_id = :b AND receiver_id = :a))",
                 a=me, b=target_id)
    await db.commit()
    return Response(status_code=204)


@router.delete("/blocks/{target_id}", status_code=204)
async def unblock_user(target_id: int, user: CurrentUser, db: DB) -> Response:
    await q_exec(db, "DELETE FROM user_blocks WHERE blocker_id = :a AND blocked_id = :b", a=user["id"], b=target_id)
    await db.commit()
    return Response(status_code=204)


# ============================================================================ жалобы
class ReportIn(BaseModel):
    target_user_id: int | None = None
    target_venue_id: int | None = None
    target_game_id: int | None = None
    reason: Literal["spam", "harassment", "inappropriate", "fake_info", "other"]
    description: str | None = None

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 1000, "Описание")

    @model_validator(mode="after")
    def _one_target(self) -> "ReportIn":
        if sum(x is not None for x in (self.target_user_id, self.target_venue_id, self.target_game_id)) != 1:
            raise ValueError("Укажите ровно один объект жалобы")
        return self


@router.post("/reports", status_code=201)
async def create_report(body: ReportIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.target_user_id is not None:
        if body.target_user_id == user["id"]:
            raise ApiError(422, "self_report", "Нельзя пожаловаться на самого себя")
        ok = await q_val(db, "SELECT EXISTS (SELECT 1 FROM users WHERE id = :id AND deleted_at IS NULL)", id=body.target_user_id)
    elif body.target_venue_id is not None:
        ok = await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id)", id=body.target_venue_id)
    else:
        ok = await q_val(db, "SELECT EXISTS (SELECT 1 FROM games WHERE id = :id)", id=body.target_game_id)
    if not ok:
        raise not_found("Объект жалобы")
    recent = await q_val(db, "SELECT count(*) FROM reports WHERE reporter_id = :u AND created_at > now() - interval '1 hour'",
                         u=user["id"])
    if recent >= 10:
        raise too_many("Слишком много жалоб за час. Попробуйте позже.", 600)
    dup = await q_val(
        db,
        "SELECT EXISTS (SELECT 1 FROM reports WHERE reporter_id = :u AND status = 'open' "
        "AND target_user_id IS NOT DISTINCT FROM CAST(:tu AS bigint) AND target_venue_id IS NOT DISTINCT FROM CAST(:tv AS bigint) "
        "AND target_game_id IS NOT DISTINCT FROM CAST(:tg AS bigint))",
        u=user["id"], tu=body.target_user_id, tv=body.target_venue_id, tg=body.target_game_id,
    )
    if dup:
        raise conflict("report_exists", "Ваша жалоба уже находится на рассмотрении")
    row = await q_one(
        db,
        "INSERT INTO reports (reporter_id, target_user_id, target_venue_id, target_game_id, reason, description) "
        "VALUES (:u, :tu, :tv, :tg, :reason, :descr) RETURNING id",
        u=user["id"], tu=body.target_user_id, tv=body.target_venue_id, tg=body.target_game_id,
        reason=body.reason, descr=body.description,
    )
    await db.commit()
    assert row is not None
    return {"id": row["id"], "status": "open"}


# ============================================================================ личные сообщения
class MessageIn(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("Сообщение не может быть пустым")
        if len(text) > 2000:
            raise ValueError("Сообщение не длиннее 2000 символов")
        return text


def serialize_message(r: dict[str, Any], me: int) -> dict[str, Any]:
    return {"id": r["id"], "sender_id": r["sender_id"], "recipient_id": r["recipient_id"], "body": r["body"],
            "created_at": r["created_at"], "read_at": r["read_at"], "mine": r["sender_id"] == me}


@router.get("/conversations")
async def conversations(user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    rows = await q_all(
        db,
        f"""
        WITH last AS (
          SELECT CASE WHEN sender_id = :me THEN recipient_id ELSE sender_id END AS other_id, max(id) AS last_id
          FROM messages WHERE sender_id = :me OR recipient_id = :me GROUP BY 1)
        SELECT {user_json('u')} AS user, m.id AS message_id, m.body, m.created_at, m.sender_id,
               (SELECT count(*) FROM messages x WHERE x.sender_id = u.id AND x.recipient_id = :me AND x.read_at IS NULL) AS unread,
               EXISTS (SELECT 1 FROM friendships f WHERE f.user_low_id = LEAST(u.id, :me)
                       AND f.user_high_id = GREATEST(u.id, :me)) AS is_friend,
               (u.last_seen_at IS NOT NULL AND u.last_seen_at > now() - make_interval(secs => :online)) AS online
        FROM last JOIN messages m ON m.id = last.last_id JOIN users u ON u.id = last.other_id
        WHERE u.is_active AND u.deleted_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE (b.blocker_id = :me AND b.blocked_id = u.id)
                          OR (b.blocker_id = u.id AND b.blocked_id = :me))
        ORDER BY m.id DESC LIMIT 100
        """,
        me=user["id"], online=settings.online_timeout_seconds,
    )
    items = []
    for r in rows:
        items.append({
            "user": public_user(r["user"]), "is_friend": r["is_friend"],
            "online": r["online"] if r["is_friend"] else None, "unread": r["unread"],
            "last_message": {"id": r["message_id"], "body": r["body"], "created_at": r["created_at"],
                             "mine": r["sender_id"] == user["id"]},
        })
    return {"items": items}


@router.get("/messages/{other_id}")
async def get_messages(
    other_id: int, user: CurrentUser, db: DB,
    before_id: int | None = Query(None, ge=1), after_id: int | None = Query(None, ge=0),
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    """История переписки. Без параметров — последние сообщения; before_id — более старые (пагинация);
    after_id — только новые (для периодического обновления открытого чата). Порядок — от старых к новым."""
    me = user["id"]
    if other_id == me:
        raise ApiError(422, "self_chat", "Нельзя переписываться с самим собой")
    other = await q_one(db, "SELECT id FROM users WHERE id = :id AND deleted_at IS NULL", id=other_id)
    if other is None:
        raise not_found("Пользователь")
    if await is_blocked_between(db, me, other_id):
        raise forbidden("Переписка недоступна из-за блокировки", "blocked")
    base = ("SELECT id, sender_id, recipient_id, body, created_at, read_at FROM messages "
            "WHERE ((sender_id = :me AND recipient_id = :o) OR (sender_id = :o AND recipient_id = :me))")
    if after_id is not None:
        rows = await q_all(db, base + " AND id > :after ORDER BY id ASC LIMIT :limit", me=me, o=other_id,
                           after=after_id, limit=limit)
        has_more = False
    else:
        rows = await q_all(
            db, base + " AND (CAST(:before AS bigint) IS NULL OR id < CAST(:before AS bigint)) ORDER BY id DESC LIMIT :limit",
            me=me, o=other_id, before=before_id, limit=limit + 1)
        has_more = len(rows) > limit
        rows = list(reversed(rows[:limit]))
    return {"items": [serialize_message(r, me) for r in rows], "has_more": has_more}


@router.post("/messages/{other_id}", status_code=201)
async def send_message(other_id: int, body: MessageIn, request: Request, user: CurrentUser, db: DB,
                       settings: SettingsDep) -> dict[str, Any]:
    me = user["id"]
    if other_id == me:
        raise ApiError(422, "self_chat", "Нельзя писать самому себе")
    if await get_active_user(db, other_id) is None:
        raise not_found("Пользователь")
    if await is_blocked_between(db, me, other_id):
        raise forbidden("Сообщение нельзя отправить из-за блокировки", "blocked")
    if not await are_friends(db, me, other_id):
        raise forbidden("Личные сообщения доступны только друзьям", "not_friends")
    limiter = request.app.state.limiter
    key = f"msg:{me}"
    if limiter.count(key, 60) >= settings.message_max_per_minute:
        raise too_many("Слишком много сообщений. Подождите немного.", limiter.retry_after(key, 60))
    row = await q_one(
        db, "INSERT INTO messages (sender_id, recipient_id, body) VALUES (:s, :r, :b) "
            "RETURNING id, sender_id, recipient_id, body, created_at, read_at",
        s=me, r=other_id, b=body.body)
    await db.commit()
    limiter.hit(key, 60)
    assert row is not None
    return serialize_message(row, me)


@router.post("/messages/{other_id}/read", status_code=204)
async def mark_read(other_id: int, user: CurrentUser, db: DB) -> Response:
    await q_exec(db, "UPDATE messages SET read_at = now() WHERE sender_id = :o AND recipient_id = :me AND read_at IS NULL",
                 o=other_id, me=user["id"])
    await db.commit()
    return Response(status_code=204)


# ============================================================================ уведомления
@router.get("/notifications")
async def list_notifications(user: CurrentUser, db: DB, limit: int = Query(30, ge=1, le=100),
                             before_id: int | None = Query(None, ge=1)) -> dict[str, Any]:
    rows = await q_all(
        db,
        "SELECT id, type, title, body, ref_id, created_at, read_at FROM notifications WHERE user_id = :u "
        "AND (CAST(:before AS bigint) IS NULL OR id < CAST(:before AS bigint)) ORDER BY id DESC LIMIT :limit",
        u=user["id"], before=before_id, limit=limit)
    unread = await q_val(db, "SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL", u=user["id"])
    return {"items": rows, "unread_count": unread}


@router.get("/notifications/unread-count")
async def unread_count(user: CurrentUser, db: DB) -> dict[str, Any]:
    n = await q_val(db, "SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL", u=user["id"])
    unread_msgs = await q_val(db, "SELECT count(*) FROM messages WHERE recipient_id = :u AND read_at IS NULL", u=user["id"])
    return {"unread_count": n, "unread_messages": unread_msgs}


@router.post("/notifications/read-all", status_code=204)
async def read_all(user: CurrentUser, db: DB) -> Response:
    await q_exec(db, "UPDATE notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL", u=user["id"])
    await db.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
async def read_one(notification_id: int, user: CurrentUser, db: DB) -> Response:
    await q_exec(db, "UPDATE notifications SET read_at = now() WHERE id = :id AND user_id = :u AND read_at IS NULL",
                 id=notification_id, u=user["id"])
    await db.commit()
    return Response(status_code=204)
