"""Заявки на новые площадки, предложения изменений и их модерация."""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from .. import validators
from ..db import as_json, q_all, q_exec, q_one, q_val
from ..deps import DB, CurrentUser, Moderator, SettingsDep, StoreDep
from ..errors import ApiError, conflict, forbidden, not_found
from ..services.common import (audit, notify, public_user, sports_json_for, valid_sport_ids, venue_photo_url,
                               user_json)

logger = logging.getLogger("sportcourts.moderation")
router = APIRouter(tags=["venue-flow"])


# ----------------------------------------------------------------------------- схема данных
class VenueIn(BaseModel):
    name: str
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    venue_type: Literal["indoor", "outdoor"]
    sport_ids: list[int] = Field(min_length=1, max_length=20)
    description: str | None = None
    work_hours: str | None = None
    cost_info: str | None = None
    photo_token: str | None = None
    force: bool = False  # подтверждение: «да, это не дубликат»

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validators.clean_text(v, 120, "Название") or _raise("Название не может быть пустым")

    @field_validator("address")
    @classmethod
    def _address(cls, v: str) -> str:
        return validators.clean_text(v, 255, "Адрес") or _raise("Адрес не может быть пустым")

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 2000, "Описание")

    @field_validator("work_hours")
    @classmethod
    def _hours(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 100, "Время работы")

    @field_validator("cost_info")
    @classmethod
    def _cost(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 100, "Стоимость")


class RejectIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        text = validators.clean_text(v, 500, "Причина")
        if not text or len(text) < 3:
            raise ValueError("Укажите причину отказа")
        return text


def _raise(message: str):
    raise ValueError(message)


# ----------------------------------------------------------------------------- дубликаты
DUPLICATES_SQL = """
SELECT * FROM (
  SELECT 'venue' AS kind, v.id, v.name, v.address,
         111320.0 * sqrt(power(v.latitude - CAST(:lat AS double precision), 2)
           + power((v.longitude - CAST(:lon AS double precision)) * cos(radians(CAST(:lat AS double precision))), 2)) AS distance_m,
         v.name AS cmp_name
  FROM venues v WHERE v.status = 'active' AND (CAST(:exclude AS bigint) IS NULL OR v.id <> CAST(:exclude AS bigint))
  UNION ALL
  SELECT 'submission', s.id, s.name, s.address,
         111320.0 * sqrt(power(s.latitude - CAST(:lat AS double precision), 2)
           + power((s.longitude - CAST(:lon AS double precision)) * cos(radians(CAST(:lat AS double precision))), 2)),
         s.name
  FROM venue_submissions s WHERE s.status = 'pending'
) d
WHERE d.distance_m <= 100
   OR lower(btrim(d.cmp_name)) = lower(btrim(CAST(:name AS text)))
   OR (d.distance_m <= 500 AND (lower(d.cmp_name) LIKE '%' || lower(btrim(CAST(:name AS text))) || '%'
                                OR lower(btrim(CAST(:name AS text))) LIKE '%' || lower(d.cmp_name) || '%'))
ORDER BY d.distance_m
LIMIT 5
"""


async def find_duplicates(db, name: str, lat: float, lon: float, exclude_venue: int | None = None) -> list[dict[str, Any]]:
    rows = await q_all(db, DUPLICATES_SQL, name=name, lat=lat, lon=lon, exclude=exclude_venue)
    return [{"kind": r["kind"], "id": r["id"], "name": r["name"], "address": r["address"],
             "distance_m": round(float(r["distance_m"]))} for r in rows]


async def ensure_no_unconfirmed_duplicates(db, body: VenueIn, exclude_venue: int | None = None) -> None:
    if body.force:
        return
    dups = await find_duplicates(db, body.name, body.latitude, body.longitude, exclude_venue)
    if dups:
        raise ApiError(
            409, "possible_duplicates",
            "Похожие площадки уже есть. Проверьте список и подтвердите отправку, если это другая площадка.",
            details={"duplicates": dups},
        )


@router.post("/venues/check-duplicates")
async def check_duplicates(body: VenueIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    return {"duplicates": await find_duplicates(db, body.name, body.latitude, body.longitude)}


# ----------------------------------------------------------------------------- пользовательские заявки
async def _adopt_photo(store, token: str | None, user_id: int) -> str | None:
    if not token:
        return None
    name = store.adopt(token, user_id, "venues")
    if name is None:
        raise ApiError(422, "invalid_photo_token", "Фото не найдено или срок его хранения истёк. Загрузите заново.")
    return name


@router.post("/venue-submissions", status_code=201)
async def submit_venue(body: VenueIn, user: CurrentUser, db: DB, settings: SettingsDep, store: StoreDep) -> dict[str, Any]:
    pending = await q_val(
        db, "SELECT count(*) FROM venue_submissions WHERE submitter_id = :u AND status = 'pending'", u=user["id"])
    if pending >= settings.max_pending_submissions_per_user:
        raise ApiError(429, "too_many_pending", "У вас уже слишком много заявок на рассмотрении. Дождитесь решения.")
    if not await valid_sport_ids(db, body.sport_ids):
        raise ApiError(422, "unknown_sport", "Выбран неизвестный вид спорта")
    await ensure_no_unconfirmed_duplicates(db, body)

    photo = await _adopt_photo(store, body.photo_token, user["id"])
    try:
        row = await q_one(
            db,
            """INSERT INTO venue_submissions (submitter_id, name, address, latitude, longitude, venue_type,
                   description, work_hours, cost_info, photo_path)
               VALUES (:u, :name, :addr, :lat, :lon, :vt, :descr, :wh, :ci, :photo) RETURNING id, created_at""",
            u=user["id"], name=body.name, addr=body.address, lat=body.latitude, lon=body.longitude,
            vt=body.venue_type, descr=body.description, wh=body.work_hours, ci=body.cost_info, photo=photo,
        )
        assert row is not None
        await q_exec(
            db, "INSERT INTO venue_submission_sports (submission_id, sport_id) "
                "SELECT :id, x FROM unnest(CAST(:ids AS integer[])) AS x",
            id=row["id"], ids=list(set(body.sport_ids)),
        )
        await db.commit()
    except Exception:
        store.delete("venues", photo)
        raise
    return {"id": row["id"], "status": "pending", "created_at": row["created_at"]}


SUBMISSION_SELECT = f"""
SELECT s.id, s.name, s.address, s.latitude, s.longitude, s.venue_type, s.description, s.work_hours,
       s.cost_info, s.photo_path, s.status, s.decision_reason, s.decided_at, s.created_at, s.venue_id,
       {sports_json_for('venue_submission_sports', 'submission_id', 's.id')} AS sports,
       {user_json('su')} AS submitter
FROM venue_submissions s JOIN users su ON su.id = s.submitter_id
"""


def serialize_submission(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"], "name": r["name"], "address": r["address"], "latitude": r["latitude"],
        "longitude": r["longitude"], "venue_type": r["venue_type"], "description": r["description"],
        "work_hours": r["work_hours"], "cost_info": r["cost_info"], "photo_url": venue_photo_url(r["photo_path"]),
        "status": r["status"], "decision_reason": r["decision_reason"], "decided_at": r["decided_at"],
        "created_at": r["created_at"], "venue_id": r["venue_id"], "sports": as_json(r["sports"], []),
        "submitter": public_user(r["submitter"]),
    }


@router.get("/venue-submissions/mine")
async def my_submissions(user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    rows = await q_all(db, SUBMISSION_SELECT + " WHERE s.submitter_id = :u ORDER BY s.id DESC LIMIT :limit",
                       u=user["id"], limit=limit)
    return {"items": [serialize_submission(r) for r in rows]}


# ----------------------------------------------------------------------------- предложения изменений
PROPOSAL_SELECT = f"""
SELECT p.id, p.venue_id, p.name, p.address, p.latitude, p.longitude, p.venue_type, p.description, p.work_hours,
       p.cost_info, p.photo_path, p.status, p.decision_reason, p.decided_at, p.created_at,
       {sports_json_for('venue_change_proposal_sports', 'proposal_id', 'p.id')} AS sports,
       {user_json('pu')} AS proposer,
       json_build_object('name', v.name, 'address', v.address, 'latitude', v.latitude, 'longitude', v.longitude,
          'venue_type', v.venue_type, 'description', v.description, 'work_hours', v.work_hours,
          'cost_info', v.cost_info, 'photo_path', v.photo_path,
          'sports', {sports_json_for('venue_sports', 'venue_id', 'v.id')}) AS current_venue
FROM venue_change_proposals p
JOIN users pu ON pu.id = p.proposer_id
JOIN venues v ON v.id = p.venue_id
"""


def serialize_proposal(r: dict[str, Any]) -> dict[str, Any]:
    cur = as_json(r["current_venue"])
    current = dict(cur)
    current["photo_url"] = venue_photo_url(current.pop("photo_path", None))
    return {
        "id": r["id"], "venue_id": r["venue_id"], "name": r["name"], "address": r["address"],
        "latitude": r["latitude"], "longitude": r["longitude"], "venue_type": r["venue_type"],
        "description": r["description"], "work_hours": r["work_hours"], "cost_info": r["cost_info"],
        "photo_url": venue_photo_url(r["photo_path"]), "status": r["status"],
        "decision_reason": r["decision_reason"], "decided_at": r["decided_at"], "created_at": r["created_at"],
        "sports": as_json(r["sports"], []), "proposer": public_user(r["proposer"]), "current": current,
    }


@router.post("/venues/{venue_id}/proposals", status_code=201)
async def propose_change(venue_id: int, body: VenueIn, user: CurrentUser, db: DB, settings: SettingsDep,
                         store: StoreDep) -> dict[str, Any]:
    if not await q_val(db, "SELECT EXISTS (SELECT 1 FROM venues WHERE id = :id AND status = 'active')", id=venue_id):
        raise not_found("Площадка")
    pending = await q_val(
        db, "SELECT count(*) FROM venue_change_proposals WHERE proposer_id = :u AND status = 'pending'", u=user["id"])
    if pending >= settings.max_pending_submissions_per_user:
        raise ApiError(429, "too_many_pending", "У вас уже слишком много предложений на рассмотрении.")
    if not await valid_sport_ids(db, body.sport_ids):
        raise ApiError(422, "unknown_sport", "Выбран неизвестный вид спорта")
    photo = await _adopt_photo(store, body.photo_token, user["id"])
    try:
        row = await q_one(
            db,
            """INSERT INTO venue_change_proposals (venue_id, proposer_id, name, address, latitude, longitude,
                   venue_type, description, work_hours, cost_info, photo_path)
               VALUES (:v, :u, :name, :addr, :lat, :lon, :vt, :descr, :wh, :ci, :photo) RETURNING id, created_at""",
            v=venue_id, u=user["id"], name=body.name, addr=body.address, lat=body.latitude, lon=body.longitude,
            vt=body.venue_type, descr=body.description, wh=body.work_hours, ci=body.cost_info, photo=photo,
        )
        assert row is not None
        await q_exec(
            db, "INSERT INTO venue_change_proposal_sports (proposal_id, sport_id) "
                "SELECT :id, x FROM unnest(CAST(:ids AS integer[])) AS x",
            id=row["id"], ids=list(set(body.sport_ids)),
        )
        await db.commit()
    except Exception:
        store.delete("venues", photo)
        raise
    return {"id": row["id"], "status": "pending", "created_at": row["created_at"]}


@router.get("/venue-change-proposals/mine")
async def my_proposals(user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    rows = await q_all(db, PROPOSAL_SELECT + " WHERE p.proposer_id = :u ORDER BY p.id DESC LIMIT :limit",
                       u=user["id"], limit=limit)
    return {"items": [serialize_proposal(r) for r in rows]}


# ----------------------------------------------------------------------------- модерация
Status = Literal["pending", "approved", "rejected"]


@router.get("/moderation/submissions")
async def mod_submissions(mod: Moderator, db: DB, status: Status = "pending",
                          limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = await q_all(
        db, SUBMISSION_SELECT + " WHERE s.status = :st ORDER BY s.id " + ("ASC" if status == "pending" else "DESC")
            + " LIMIT :limit OFFSET :offset", st=status, limit=limit, offset=offset)
    out = []
    for r in rows:
        item = serialize_submission(r)
        if status == "pending":
            item["duplicates"] = await find_duplicates(db, r["name"], r["latitude"], r["longitude"])
            item["duplicates"] = [d for d in item["duplicates"] if not (d["kind"] == "submission" and d["id"] == r["id"])]
        out.append(item)
    return {"items": out}


@router.post("/moderation/submissions/{submission_id}/approve")
async def approve_submission(submission_id: int, mod: Moderator, db: DB) -> dict[str, Any]:
    sub = await q_one(db, "SELECT * FROM venue_submissions WHERE id = :id FOR UPDATE", id=submission_id)
    if sub is None:
        raise not_found("Заявка")
    if sub["status"] != "pending":
        raise conflict("already_decided", "По этой заявке уже принято решение")
    if sub["submitter_id"] == mod["id"] and mod["role"] != "admin":
        raise forbidden("Нельзя рассматривать собственную заявку", "own_submission")
    venue = await q_one(
        db,
        """INSERT INTO venues (name, address, latitude, longitude, venue_type, description, work_hours, cost_info,
               photo_path, created_by)
           VALUES (:name, :addr, :lat, :lon, :vt, :descr, :wh, :ci, :photo, :by) RETURNING id""",
        name=sub["name"], addr=sub["address"], lat=sub["latitude"], lon=sub["longitude"], vt=sub["venue_type"],
        descr=sub["description"], wh=sub["work_hours"], ci=sub["cost_info"], photo=sub["photo_path"],
        by=sub["submitter_id"],
    )
    assert venue is not None
    await q_exec(db, "INSERT INTO venue_sports (venue_id, sport_id) SELECT :v, sport_id "
                     "FROM venue_submission_sports WHERE submission_id = :s", v=venue["id"], s=submission_id)
    await q_exec(
        db, "UPDATE venue_submissions SET status = 'approved', decided_by = :m, decided_at = now(), venue_id = :v "
            "WHERE id = :id", m=mod["id"], v=venue["id"], id=submission_id)
    await q_exec(db, "INSERT INTO moderation_decisions (kind, submission_id, moderator_id, decision) "
                     "VALUES ('venue_submission', :id, :m, 'approved')", id=submission_id, m=mod["id"])
    await notify(db, sub["submitter_id"], "venue_submission_decided", "Площадка одобрена",
                 f"Площадка «{sub['name']}» добавлена на карту.", venue["id"])
    await audit(db, mod["id"], "venue_submission_approved", "venue_submission", submission_id)
    await db.commit()
    return {"status": "approved", "venue_id": venue["id"]}


@router.post("/moderation/submissions/{submission_id}/reject")
async def reject_submission(submission_id: int, body: RejectIn, mod: Moderator, db: DB, store: StoreDep) -> dict[str, Any]:
    sub = await q_one(db, "SELECT * FROM venue_submissions WHERE id = :id FOR UPDATE", id=submission_id)
    if sub is None:
        raise not_found("Заявка")
    if sub["status"] != "pending":
        raise conflict("already_decided", "По этой заявке уже принято решение")
    if sub["submitter_id"] == mod["id"] and mod["role"] != "admin":
        raise forbidden("Нельзя рассматривать собственную заявку", "own_submission")
    await q_exec(
        db, "UPDATE venue_submissions SET status = 'rejected', decided_by = :m, decided_at = now(), "
            "decision_reason = :r, photo_path = NULL WHERE id = :id", m=mod["id"], r=body.reason, id=submission_id)
    await q_exec(db, "INSERT INTO moderation_decisions (kind, submission_id, moderator_id, decision, reason) "
                     "VALUES ('venue_submission', :id, :m, 'rejected', :r)", id=submission_id, m=mod["id"], r=body.reason)
    await notify(db, sub["submitter_id"], "venue_submission_decided", "Площадка отклонена",
                 f"Заявка на «{sub['name']}» отклонена. Причина: {body.reason}", None)
    await audit(db, mod["id"], "venue_submission_rejected", "venue_submission", submission_id, body.reason)
    await db.commit()
    store.delete("venues", sub["photo_path"])
    return {"status": "rejected"}


@router.get("/moderation/proposals")
async def mod_proposals(mod: Moderator, db: DB, status: Status = "pending",
                        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = await q_all(
        db, PROPOSAL_SELECT + " WHERE p.status = :st ORDER BY p.id " + ("ASC" if status == "pending" else "DESC")
            + " LIMIT :limit OFFSET :offset", st=status, limit=limit, offset=offset)
    return {"items": [serialize_proposal(r) for r in rows]}


@router.post("/moderation/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: int, mod: Moderator, db: DB, store: StoreDep) -> dict[str, Any]:
    p = await q_one(db, "SELECT * FROM venue_change_proposals WHERE id = :id FOR UPDATE", id=proposal_id)
    if p is None:
        raise not_found("Предложение")
    if p["status"] != "pending":
        raise conflict("already_decided", "По этому предложению уже принято решение")
    if p["proposer_id"] == mod["id"] and mod["role"] != "admin":
        raise forbidden("Нельзя рассматривать собственное предложение", "own_submission")
    venue = await q_one(db, "SELECT id, photo_path, status FROM venues WHERE id = :id FOR UPDATE", id=p["venue_id"])
    if venue is None or venue["status"] != "active":
        raise conflict("venue_archived", "Площадка уже снята с публикации")
    new_photo = p["photo_path"] or venue["photo_path"]
    await q_exec(
        db,
        """UPDATE venues SET name = :name, address = :addr, latitude = :lat, longitude = :lon, venue_type = :vt,
               description = :descr, work_hours = :wh, cost_info = :ci, photo_path = :photo, updated_at = now()
           WHERE id = :id""",
        name=p["name"], addr=p["address"], lat=p["latitude"], lon=p["longitude"], vt=p["venue_type"],
        descr=p["description"], wh=p["work_hours"], ci=p["cost_info"], photo=new_photo, id=venue["id"],
    )
    await q_exec(db, "DELETE FROM venue_sports WHERE venue_id = :v", v=venue["id"])
    await q_exec(db, "INSERT INTO venue_sports (venue_id, sport_id) SELECT :v, sport_id "
                     "FROM venue_change_proposal_sports WHERE proposal_id = :p", v=venue["id"], p=proposal_id)
    await q_exec(db, "UPDATE venue_change_proposals SET status = 'approved', decided_by = :m, decided_at = now() "
                     "WHERE id = :id", m=mod["id"], id=proposal_id)
    await q_exec(db, "INSERT INTO moderation_decisions (kind, proposal_id, moderator_id, decision) "
                     "VALUES ('venue_change', :id, :m, 'approved')", id=proposal_id, m=mod["id"])
    await notify(db, p["proposer_id"], "venue_change_decided", "Изменения одобрены",
                 f"Изменения площадки «{p['name']}» применены.", venue["id"])
    await audit(db, mod["id"], "venue_change_approved", "venue_change_proposal", proposal_id)
    await db.commit()
    if p["photo_path"] and venue["photo_path"] and venue["photo_path"] != p["photo_path"]:
        store.delete("venues", venue["photo_path"])  # старое фото больше не используется
    return {"status": "approved", "venue_id": venue["id"]}


@router.post("/moderation/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: int, body: RejectIn, mod: Moderator, db: DB, store: StoreDep) -> dict[str, Any]:
    p = await q_one(db, "SELECT * FROM venue_change_proposals WHERE id = :id FOR UPDATE", id=proposal_id)
    if p is None:
        raise not_found("Предложение")
    if p["status"] != "pending":
        raise conflict("already_decided", "По этому предложению уже принято решение")
    if p["proposer_id"] == mod["id"] and mod["role"] != "admin":
        raise forbidden("Нельзя рассматривать собственное предложение", "own_submission")
    await q_exec(
        db, "UPDATE venue_change_proposals SET status = 'rejected', decided_by = :m, decided_at = now(), "
            "decision_reason = :r, photo_path = NULL WHERE id = :id", m=mod["id"], r=body.reason, id=proposal_id)
    await q_exec(db, "INSERT INTO moderation_decisions (kind, proposal_id, moderator_id, decision, reason) "
                     "VALUES ('venue_change', :id, :m, 'rejected', :r)", id=proposal_id, m=mod["id"], r=body.reason)
    await notify(db, p["proposer_id"], "venue_change_decided", "Изменения отклонены",
                 f"Предложение по «{p['name']}» отклонено. Причина: {body.reason}", p["venue_id"])
    await audit(db, mod["id"], "venue_change_rejected", "venue_change_proposal", proposal_id, body.reason)
    await db.commit()
    store.delete("venues", p["photo_path"])
    return {"status": "rejected"}


@router.get("/moderation/decisions")
async def decisions_history(mod: Moderator, db: DB, limit: int = Query(50, ge=1, le=200),
                            offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = await q_all(
        db,
        f"""
        SELECT d.id, d.kind, d.decision, d.reason, d.created_at, d.submission_id, d.proposal_id,
               {user_json('m')} AS moderator,
               coalesce(s.name, p.name) AS venue_name
        FROM moderation_decisions d
        LEFT JOIN users m ON m.id = d.moderator_id
        LEFT JOIN venue_submissions s ON s.id = d.submission_id
        LEFT JOIN venue_change_proposals p ON p.id = d.proposal_id
        ORDER BY d.id DESC LIMIT :limit OFFSET :offset
        """,
        limit=limit, offset=offset,
    )
    for r in rows:
        r["moderator"] = public_user(r["moderator"]) if r["moderator"] and as_json(r["moderator"]).get("id") else None
    return {"items": rows}
