"""Каталог площадок, личное присутствие, отчёты о числе игроков, фото."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from pydantic import BaseModel, Field

from .. import validators
from ..db import as_json, q_all, q_exec, q_one, q_val
from ..deps import DB, CurrentUser, SettingsDep, StoreDep
from ..errors import ApiError, conflict, not_found, too_many
from ..images import ImageLimits, process_image
from ..services.common import public_user, sports_json_for, venue_photo_url

router = APIRouter(tags=["venues"])

# ----------------------------------------------------------------------------- SQL
# Выражение расстояния (км) по формуле гаверсинусов; NULL, если координаты пользователя не заданы.
_DIST = (
    "6371.0 * 2 * asin(sqrt(least(1.0, power(sin(radians(v.latitude - CAST(:lat AS double precision)) / 2), 2) "
    "+ cos(radians(CAST(:lat AS double precision))) * cos(radians(v.latitude)) "
    "* power(sin(radians(v.longitude - CAST(:lon AS double precision)) / 2), 2))))"
)

VENUE_SELECT = f"""
SELECT v.id, v.name, v.address, v.latitude, v.longitude, v.venue_type, v.description,
       v.work_hours, v.cost_info, v.photo_path, v.status,
       {sports_json_for('venue_sports', 'venue_id', 'v.id')} AS sports,
       (SELECT count(*) FROM presence_checkins p WHERE p.venue_id = v.id AND p.ended_at IS NULL
          AND p.expires_at > now()) AS checked_in_count,
       lr.player_count AS reported_players, lr.created_at AS reported_at,
       (lr.created_at IS NOT NULL AND lr.created_at > now() - make_interval(hours => :report_ttl)) AS report_fresh,
       (SELECT count(*) FROM games g WHERE g.venue_id = v.id AND g.status = 'open'
          AND g.starts_at > now() - make_interval(hours => :grace)) AS open_games_count,
       CASE WHEN CAST(:lat AS double precision) IS NULL OR CAST(:lon AS double precision) IS NULL
            THEN NULL ELSE {_DIST} END AS distance_km
FROM venues v
LEFT JOIN LATERAL (SELECT r.player_count, r.created_at FROM player_reports r WHERE r.venue_id = v.id
                   ORDER BY r.created_at DESC, r.id DESC LIMIT 1) lr ON TRUE
"""

LIST_SQL = f"""
WITH base AS ({VENUE_SELECT} WHERE v.status = 'active')
SELECT base.*, count(*) OVER () AS total,
       GREATEST(base.checked_in_count, CASE WHEN base.report_fresh THEN base.reported_players ELSE 0 END)
         AS players_estimate
FROM base
WHERE (CAST(:q AS text) IS NULL OR base.name ILIKE CAST(:q AS text) ESCAPE '\\'
       OR base.address ILIKE CAST(:q AS text) ESCAPE '\\')
  AND (CAST(:sport AS integer) IS NULL OR EXISTS (SELECT 1 FROM venue_sports vs
         WHERE vs.venue_id = base.id AND vs.sport_id = CAST(:sport AS integer)))
  AND (CAST(:vtype AS text) IS NULL OR base.venue_type = CAST(:vtype AS text))
  AND (CAST(:radius AS double precision) IS NULL OR base.distance_km IS NULL
       OR base.distance_km <= CAST(:radius AS double precision))
  AND (CAST(:min_players AS integer) IS NULL OR
       GREATEST(base.checked_in_count, CASE WHEN base.report_fresh THEN base.reported_players ELSE 0 END)
         >= CAST(:min_players AS integer))
ORDER BY
  CASE WHEN CAST(:sort AS text) = 'distance' THEN base.distance_km END ASC NULLS LAST,
  CASE WHEN CAST(:sort AS text) = 'players' THEN
       GREATEST(base.checked_in_count, CASE WHEN base.report_fresh THEN base.reported_players ELSE 0 END) END DESC NULLS LAST,
  lower(base.name), base.id
LIMIT :limit OFFSET :offset
"""


def serialize_venue(row: dict[str, Any], detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"],
        "name": row["name"],
        "address": row["address"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "venue_type": row["venue_type"],
        "work_hours": row["work_hours"],
        "cost_info": row["cost_info"],
        "photo_url": venue_photo_url(row["photo_path"]),
        "sports": as_json(row["sports"], []),
        "checked_in_count": row["checked_in_count"],
        "latest_report": (
            {"player_count": row["reported_players"], "reported_at": row["reported_at"],
             "is_fresh": bool(row["report_fresh"])}
            if row["reported_at"] is not None else None
        ),
        "open_games_count": row["open_games_count"],
        "distance_km": None if row["distance_km"] is None else round(float(row["distance_km"]), 3),
        "status": row["status"],
    }
    if "players_estimate" in row:
        out["players_estimate"] = row["players_estimate"]
    if detail:
        out["description"] = row["description"]
    return out


def venue_params(settings, lat: float | None = None, lon: float | None = None) -> dict[str, Any]:
    return {"lat": lat, "lon": lon, "report_ttl": settings.player_report_ttl_hours,
            "grace": settings.game_list_grace_hours}


# ----------------------------------------------------------------------------- список и карточка
@router.get("/venues")
async def list_venues(
    user: CurrentUser, db: DB, settings: SettingsDep,
    q: str | None = Query(None, max_length=100),
    sport_id: int | None = None,
    venue_type: Literal["indoor", "outdoor"] | None = None,
    min_players: int | None = Query(None, ge=0, le=200),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_km: float | None = Query(None, gt=0, le=20000),
    sort: Literal["distance", "name", "players"] = "name",
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    if (lat is None) != (lon is None):
        raise ApiError(422, "validation_error", "Укажите обе координаты: lat и lon")
    if sort == "distance" and lat is None:
        sort = "name"
    pattern = validators.like_pattern(q.strip()) if q and q.strip() else None
    rows = await q_all(
        db, LIST_SQL, q=pattern, sport=sport_id, vtype=venue_type, radius=radius_km, min_players=min_players,
        sort=sort, limit=limit, offset=offset, **venue_params(settings, lat, lon),
    )
    return {
        "items": [serialize_venue(r) for r in rows],
        "total": rows[0]["total"] if rows else 0,
        "limit": limit, "offset": offset,
    }


async def load_venue(db, settings, venue_id: int, lat: float | None = None, lon: float | None = None,
                     include_archived: bool = False) -> dict[str, Any]:
    row = await q_one(
        db, VENUE_SELECT + " WHERE v.id = :id AND (v.status = 'active' OR CAST(:arch AS boolean))",
        id=venue_id, arch=include_archived, **venue_params(settings, lat, lon),
    )
    if row is None:
        raise not_found("Площадка")
    return row


@router.get("/venues/{venue_id}")
async def get_venue(
    venue_id: int, user: CurrentUser, db: DB, settings: SettingsDep,
    lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
) -> dict[str, Any]:
    row = await load_venue(db, settings, venue_id, lat, lon)
    out = serialize_venue(row, detail=True)
    mine = await q_one(
        db,
        "SELECT expires_at FROM presence_checkins WHERE user_id = :u AND venue_id = :v "
        "AND ended_at IS NULL AND expires_at > now()",
        u=user["id"], v=venue_id,
    )
    out["my_presence"] = {"active": mine is not None, "expires_at": mine["expires_at"] if mine else None}
    return out


# ----------------------------------------------------------------------------- присутствие
@router.post("/venues/{venue_id}/presence/toggle")
async def toggle_presence(venue_id: int, user: CurrentUser, db: DB, settings: SettingsDep) -> dict[str, Any]:
    """Повторное нажатие переключает отметку «я на площадке». Активная отметка истекает через 3 часа."""
    exists = await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id AND status = 'active')", id=venue_id)
    if not exists:
        raise not_found("Площадка")
    # сериализуем действия одного пользователя: двойной тап не создаст две записи
    await q_exec(db, "SELECT pg_advisory_xact_lock(CAST(:k AS bigint))", k=user["id"])
    await q_exec(
        db,
        "UPDATE presence_checkins SET ended_at = expires_at, end_reason = 'expired' "
        "WHERE user_id = :u AND ended_at IS NULL AND expires_at <= now()",
        u=user["id"],
    )
    current = await q_one(
        db, "SELECT id, venue_id FROM presence_checkins WHERE user_id = :u AND ended_at IS NULL FOR UPDATE",
        u=user["id"],
    )
    active, expires_at = False, None
    if current is not None and current["venue_id"] == venue_id:
        await q_exec(db, "UPDATE presence_checkins SET ended_at = now(), end_reason = 'manual' WHERE id = :id",
                     id=current["id"])
    else:
        if current is not None:
            await q_exec(db, "UPDATE presence_checkins SET ended_at = now(), end_reason = 'moved' WHERE id = :id",
                         id=current["id"])
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.presence_ttl_hours)
        await q_exec(
            db, "INSERT INTO presence_checkins (user_id, venue_id, expires_at) VALUES (:u, :v, :e)",
            u=user["id"], v=venue_id, e=expires_at,
        )
        active = True
    await db.commit()
    count = await q_val(
        db,
        "SELECT count(*) FROM presence_checkins WHERE venue_id = :v AND ended_at IS NULL AND expires_at > now()",
        v=venue_id,
    )
    return {"active": active, "expires_at": expires_at, "checked_in_count": count}


# ----------------------------------------------------------------------------- отчёты о числе игроков
class PlayerReportIn(BaseModel):
    player_count: int = Field(ge=0, le=200)


@router.post("/venues/{venue_id}/player-reports", status_code=201)
async def create_player_report(venue_id: int, body: PlayerReportIn, user: CurrentUser, db: DB,
                               settings: SettingsDep) -> dict[str, Any]:
    exists = await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id AND status = 'active')", id=venue_id)
    if not exists:
        raise not_found("Площадка")
    await q_exec(db, "SELECT pg_advisory_xact_lock(CAST(:k AS bigint))", k=user["id"])
    last = await q_val(
        db, "SELECT max(created_at) FROM player_reports WHERE reporter_id = :u AND venue_id = :v",
        u=user["id"], v=venue_id,
    )
    now = datetime.now(timezone.utc)
    if last is not None:
        wait = settings.player_report_cooldown_seconds - (now - last).total_seconds()
        if wait > 0:
            raise too_many("Вы уже сообщали число игроков на этой площадке. Подождите немного.", int(wait) + 1)
    per_hour = await q_val(
        db, "SELECT count(*) FROM player_reports WHERE reporter_id = :u AND created_at > now() - interval '1 hour'",
        u=user["id"],
    )
    if per_hour >= settings.player_report_max_per_hour:
        raise too_many("Слишком много отчётов за час. Попробуйте позже.", 600)
    row = await q_one(
        db, "INSERT INTO player_reports (venue_id, reporter_id, player_count) VALUES (:v, :u, :c) "
            "RETURNING id, player_count, created_at",
        v=venue_id, u=user["id"], c=body.player_count,
    )
    await db.commit()
    assert row is not None
    return {"id": row["id"], "player_count": row["player_count"], "reported_at": row["created_at"]}


@router.get("/venues/{venue_id}/player-reports")
async def list_player_reports(venue_id: int, user: CurrentUser, db: DB,
                              limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    if not await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id)", id=venue_id):
        raise not_found("Площадка")
    rows = await q_all(
        db,
        """
        SELECT r.id, r.player_count, r.created_at AS reported_at,
               json_build_object('id', u.id, 'login', u.login, 'display_name', u.display_name,
                                 'avatar_path', u.avatar_path) AS reporter
        FROM player_reports r JOIN users u ON u.id = r.reporter_id
        WHERE r.venue_id = :v ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset
        """,
        v=venue_id, limit=limit, offset=offset,
    )
    for r in rows:
        r["reporter"] = public_user(r["reporter"])
    return {"items": rows, "limit": limit, "offset": offset}


# ----------------------------------------------------------------------------- фото
@router.post("/uploads/venue-photo", status_code=201)
async def upload_venue_photo(request: Request, user: CurrentUser, settings: SettingsDep, store: StoreDep,
                             file: UploadFile = File(...)) -> dict[str, Any]:
    """Загружает и обрабатывает фото. Возвращает токен, который передаётся при отправке заявки на площадку."""
    limiter = request.app.state.limiter
    key = f"upload:{user['id']}"
    if limiter.count(key, 3600) >= 30:
        raise too_many("Слишком много загрузок. Попробуйте позже.", limiter.retry_after(key, 3600))
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    limits = ImageLimits(settings.max_upload_mb * 1024 * 1024, settings.image_max_dimension,
                         settings.image_max_pixels, settings.jpeg_quality)
    jpeg = process_image(data, limits)
    limiter.hit(key, 3600)
    return {"token": store.stage(user["id"], jpeg), "size_bytes": len(jpeg)}
