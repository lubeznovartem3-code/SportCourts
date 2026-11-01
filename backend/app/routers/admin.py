"""Административные операции, заявки на роль модератора, рассмотрение жалоб."""
from __future__ import annotations

import logging
import shutil
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, field_validator

from .. import passwords, validators
from ..db import as_json, check_database, check_collation, q_all, q_exec, q_one, q_val
from ..deps import DB, Admin, CurrentUser, ReportReviewer, SettingsDep, StoreDep
from ..errors import ApiError, conflict, forbidden, not_found
from ..services.common import (audit, list_sports, notify, public_user, user_json, valid_sport_ids)
from .venue_flow import RejectIn, VenueIn, _adopt_photo, ensure_no_unconfirmed_duplicates
from .venues import load_venue, serialize_venue

logger = logging.getLogger("sportcourts.admin")
router = APIRouter(tags=["admin"])


# ============================================================================ заявки на роль модератора
class ModeratorRequestIn(BaseModel):
    message: str | None = None

    @field_validator("message")
    @classmethod
    def _m(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 500, "Сообщение")


@router.post("/moderator-requests", status_code=201)
async def request_moderator(body: ModeratorRequestIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    if user["role"] != "user":
        raise conflict("already_privileged", "У вас уже есть расширенные права")
    exists = await q_val(
        db, "SELECT EXISTS (SELECT 1 FROM moderator_requests WHERE user_id = :u AND status = 'pending')", u=user["id"])
    if exists:
        raise conflict("request_exists", "Ваша заявка уже на рассмотрении")
    row = await q_one(db, "INSERT INTO moderator_requests (user_id, message) VALUES (:u, :m) RETURNING id",
                      u=user["id"], m=body.message)
    await db.commit()
    assert row is not None
    return {"id": row["id"], "status": "pending"}


@router.get("/moderator-requests/mine")
async def my_moderator_requests(user: CurrentUser, db: DB) -> dict[str, Any]:
    rows = await q_all(
        db, "SELECT id, message, status, decision_reason, created_at, decided_at FROM moderator_requests "
            "WHERE user_id = :u ORDER BY id DESC LIMIT 20", u=user["id"])
    return {"items": rows}


@router.get("/admin/moderator-requests")
async def list_moderator_requests(admin: Admin, db: DB,
                                  status: Literal["pending", "approved", "rejected"] = "pending") -> dict[str, Any]:
    rows = await q_all(
        db,
        f"SELECT r.id, r.message, r.status, r.decision_reason, r.created_at, r.decided_at, {user_json('u')} AS user "
        "FROM moderator_requests r JOIN users u ON u.id = r.user_id WHERE r.status = :st ORDER BY r.id DESC LIMIT 100",
        st=status)
    for r in rows:
        r["user"] = public_user(r["user"])
    return {"items": rows}


@router.post("/admin/moderator-requests/{request_id}/approve")
async def approve_moderator(request_id: int, admin: Admin, db: DB) -> dict[str, Any]:
    r = await q_one(db, "SELECT * FROM moderator_requests WHERE id = :id FOR UPDATE", id=request_id)
    if r is None:
        raise not_found("Заявка")
    if r["status"] != "pending":
        raise conflict("already_decided", "По заявке уже принято решение")
    await q_exec(db, "UPDATE moderator_requests SET status = 'approved', decided_by = :a, decided_at = now() WHERE id = :id",
                 a=admin["id"], id=request_id)
    changed = await q_exec(db, "UPDATE users SET role = 'moderator' WHERE id = :u AND role = 'user' AND is_active AND deleted_at IS NULL",
                           u=r["user_id"])
    if changed:
        await notify(db, r["user_id"], "moderator_request_decided", "Вы назначены модератором",
                     "Администратор одобрил вашу заявку.", None)
    await audit(db, admin["id"], "moderator_request_approved", "user", r["user_id"])
    await db.commit()
    return {"status": "approved"}


@router.post("/admin/moderator-requests/{request_id}/reject")
async def reject_moderator(request_id: int, body: RejectIn, admin: Admin, db: DB) -> dict[str, Any]:
    r = await q_one(db, "SELECT * FROM moderator_requests WHERE id = :id FOR UPDATE", id=request_id)
    if r is None:
        raise not_found("Заявка")
    if r["status"] != "pending":
        raise conflict("already_decided", "По заявке уже принято решение")
    await q_exec(db, "UPDATE moderator_requests SET status = 'rejected', decided_by = :a, decided_at = now(), "
                     "decision_reason = :r WHERE id = :id", a=admin["id"], r=body.reason, id=request_id)
    await notify(db, r["user_id"], "moderator_request_decided", "Заявка на модератора отклонена", body.reason, None)
    await audit(db, admin["id"], "moderator_request_rejected", "user", r["user_id"], body.reason)
    await db.commit()
    return {"status": "rejected"}


# ============================================================================ пользователи
class RoleIn(BaseModel):
    role: Literal["user", "moderator"]


class ActiveIn(BaseModel):
    is_active: bool


class ReviewFlagIn(BaseModel):
    can_review_reports: bool


async def _target_user(db, user_id: int) -> dict[str, Any]:
    row = await q_one(db, "SELECT id, login, role, is_active FROM users WHERE id = :id AND deleted_at IS NULL FOR UPDATE", id=user_id)
    if row is None:
        raise not_found("Пользователь")
    return row


@router.get("/admin/users")
async def admin_users(admin: Admin, db: DB, q: str | None = Query(None, max_length=64),
                      role: Literal["user", "moderator", "admin"] | None = None,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    pat = validators.like_pattern(q.strip()) if q and q.strip() else None
    rows = await q_all(
        db,
        """SELECT u.id, u.login, u.display_name, u.avatar_path, u.role, u.is_active, u.can_review_reports,
                  u.must_change_password, u.created_at, u.last_seen_at
           FROM users u WHERE u.deleted_at IS NULL
             AND (CAST(:pat AS text) IS NULL OR u.login ILIKE CAST(:pat AS text) ESCAPE '\\'
                  OR u.display_name ILIKE CAST(:pat AS text) ESCAPE '\\')
             AND (CAST(:role AS text) IS NULL OR u.role = CAST(:role AS text))
           ORDER BY u.id DESC LIMIT :limit OFFSET :offset""",
        pat=pat, role=role, limit=limit, offset=offset)
    items = []
    for r in rows:
        item = public_user({"id": r["id"], "login": r["login"], "display_name": r["display_name"],
                            "avatar_path": r["avatar_path"]})
        item.update({k: r[k] for k in ("role", "is_active", "can_review_reports", "must_change_password",
                                       "created_at", "last_seen_at")})
        items.append(item)
    return {"items": items}


@router.put("/admin/users/{user_id}/role")
async def set_role(user_id: int, body: RoleIn, admin: Admin, db: DB) -> dict[str, Any]:
    if user_id == admin["id"]:
        raise forbidden("Нельзя менять собственную роль", "self_change")
    target = await _target_user(db, user_id)
    if target["role"] == "admin":
        raise forbidden("Права администратора меняются только через командную строку сервера", "admin_protected")
    await q_exec(db, "UPDATE users SET role = :r, can_review_reports = CASE WHEN :r = 'user' THEN FALSE ELSE can_review_reports END "
                     "WHERE id = :id", r=body.role, id=user_id)
    await audit(db, admin["id"], "role_changed", "user", user_id, f"{target['role']} -> {body.role}")
    await db.commit()
    return {"id": user_id, "role": body.role}


@router.put("/admin/users/{user_id}/review-reports")
async def set_review_flag(user_id: int, body: ReviewFlagIn, admin: Admin, db: DB) -> dict[str, Any]:
    target = await _target_user(db, user_id)
    if target["role"] != "moderator":
        raise conflict("not_moderator", "Право рассматривать жалобы выдаётся только модераторам")
    await q_exec(db, "UPDATE users SET can_review_reports = :f WHERE id = :id", f=body.can_review_reports, id=user_id)
    await audit(db, admin["id"], "review_reports_flag", "user", user_id, str(body.can_review_reports))
    await db.commit()
    return {"id": user_id, "can_review_reports": body.can_review_reports}


@router.put("/admin/users/{user_id}/active")
async def set_active(user_id: int, body: ActiveIn, admin: Admin, db: DB) -> dict[str, Any]:
    if user_id == admin["id"]:
        raise forbidden("Нельзя отключить собственный аккаунт", "self_change")
    target = await _target_user(db, user_id)
    if target["role"] == "admin":
        raise forbidden("Аккаунт администратора защищён", "admin_protected")
    await q_exec(db, "UPDATE users SET is_active = :a WHERE id = :id", a=body.is_active, id=user_id)
    if not body.is_active:
        await q_exec(db, "UPDATE user_sessions SET revoked_at = now() WHERE user_id = :id AND revoked_at IS NULL", id=user_id)
        await q_exec(db, "UPDATE presence_checkins SET ended_at = now(), end_reason = 'manual' "
                         "WHERE user_id = :id AND ended_at IS NULL", id=user_id)
    await audit(db, admin["id"], "account_enabled" if body.is_active else "account_disabled", "user", user_id)
    await db.commit()
    return {"id": user_id, "is_active": body.is_active}


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(user_id: int, admin: Admin, db: DB) -> dict[str, Any]:
    """Создаёт временный пароль (показывается один раз). Старый пароль не нужен и не виден."""
    target = await _target_user(db, user_id)
    if target["role"] == "admin":
        raise forbidden("Пароль администратора сбрасывается только через командную строку сервера", "admin_protected")
    temp = passwords.generate_temporary_password()
    await q_exec(db, "UPDATE users SET password_hash = :ph, must_change_password = TRUE WHERE id = :id",
                 ph=await passwords.hash_password_async(temp), id=user_id)
    await q_exec(db, "UPDATE user_sessions SET revoked_at = now() WHERE user_id = :id AND revoked_at IS NULL", id=user_id)
    await audit(db, admin["id"], "password_reset", "user", user_id)  # сам пароль нигде не логируется
    await db.commit()
    return {"id": user_id, "login": target["login"], "temporary_password": temp}


# ============================================================================ площадки и виды спорта
@router.post("/admin/venues", status_code=201)
async def admin_create_venue(body: VenueIn, admin: Admin, db: DB, settings: SettingsDep, store: StoreDep) -> dict[str, Any]:
    if not await valid_sport_ids(db, body.sport_ids):
        raise ApiError(422, "unknown_sport", "Выбран неизвестный вид спорта")
    await ensure_no_unconfirmed_duplicates(db, body)
    photo = await _adopt_photo(store, body.photo_token, admin["id"])
    try:
        row = await q_one(
            db,
            """INSERT INTO venues (name, address, latitude, longitude, venue_type, description, work_hours, cost_info,
                   photo_path, created_by) VALUES (:name, :addr, :lat, :lon, :vt, :descr, :wh, :ci, :photo, :by) RETURNING id""",
            name=body.name, addr=body.address, lat=body.latitude, lon=body.longitude, vt=body.venue_type,
            descr=body.description, wh=body.work_hours, ci=body.cost_info, photo=photo, by=admin["id"])
        assert row is not None
        await q_exec(db, "INSERT INTO venue_sports (venue_id, sport_id) SELECT :v, x FROM unnest(CAST(:ids AS integer[])) AS x",
                     v=row["id"], ids=list(set(body.sport_ids)))
        await audit(db, admin["id"], "venue_created", "venue", row["id"], body.name)
        await db.commit()
    except Exception:
        store.delete("venues", photo)
        raise
    return serialize_venue(await load_venue(db, settings, row["id"]), detail=True)


@router.put("/admin/venues/{venue_id}")
async def admin_update_venue(venue_id: int, body: VenueIn, admin: Admin, db: DB, settings: SettingsDep,
                             store: StoreDep) -> dict[str, Any]:
    old = await q_one(db, "SELECT id, photo_path FROM venues WHERE id = :id FOR UPDATE", id=venue_id)
    if old is None:
        raise not_found("Площадка")
    if not await valid_sport_ids(db, body.sport_ids):
        raise ApiError(422, "unknown_sport", "Выбран неизвестный вид спорта")
    photo = await _adopt_photo(store, body.photo_token, admin["id"])
    try:
        await q_exec(
            db,
            """UPDATE venues SET name = :name, address = :addr, latitude = :lat, longitude = :lon, venue_type = :vt,
                   description = :descr, work_hours = :wh, cost_info = :ci, photo_path = coalesce(:photo, photo_path),
                   updated_at = now() WHERE id = :id""",
            name=body.name, addr=body.address, lat=body.latitude, lon=body.longitude, vt=body.venue_type,
            descr=body.description, wh=body.work_hours, ci=body.cost_info, photo=photo, id=venue_id)
        await q_exec(db, "DELETE FROM venue_sports WHERE venue_id = :v", v=venue_id)
        await q_exec(db, "INSERT INTO venue_sports (venue_id, sport_id) SELECT :v, x FROM unnest(CAST(:ids AS integer[])) AS x",
                     v=venue_id, ids=list(set(body.sport_ids)))
        await audit(db, admin["id"], "venue_updated", "venue", venue_id)
        await db.commit()
    except Exception:
        store.delete("venues", photo)
        raise
    if photo and old["photo_path"]:
        store.delete("venues", old["photo_path"])
    return serialize_venue(await load_venue(db, settings, venue_id, include_archived=True), detail=True)


class ArchiveIn(BaseModel):
    archived: bool


@router.put("/admin/venues/{venue_id}/archive")
async def admin_archive_venue(venue_id: int, body: ArchiveIn, admin: Admin, db: DB) -> dict[str, Any]:
    changed = await q_exec(db, "UPDATE venues SET status = :s, updated_at = now() WHERE id = :id",
                           s="archived" if body.archived else "active", id=venue_id)
    if not changed:
        raise not_found("Площадка")
    if body.archived:  # активные отметки на скрытой площадке закрываем
        await q_exec(db, "UPDATE presence_checkins SET ended_at = now(), end_reason = 'manual' "
                         "WHERE venue_id = :id AND ended_at IS NULL", id=venue_id)
    await audit(db, admin["id"], "venue_archived" if body.archived else "venue_restored", "venue", venue_id)
    await db.commit()
    return {"id": venue_id, "status": "archived" if body.archived else "active"}


class SportIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _n(cls, v: str) -> str:
        t = validators.clean_text(v, 40, "Название")
        if not t:
            raise ValueError("Название не может быть пустым")
        return t


class SportPatch(BaseModel):
    name: str | None = None
    is_active: bool | None = None


@router.get("/admin/sports")
async def admin_sports(admin: Admin, db: DB) -> dict[str, Any]:
    return {"items": await list_sports(db, include_inactive=True)}


@router.post("/admin/sports", status_code=201)
async def admin_add_sport(body: SportIn, admin: Admin, db: DB) -> dict[str, Any]:
    from sqlalchemy.exc import IntegrityError
    code = "s" + str(await q_val(db, "SELECT coalesce(max(id), 0) + 1 FROM sports"))
    try:
        row = await q_one(db, "INSERT INTO sports (code, name, sort_order) VALUES (:c, :n, 100) RETURNING id, code, name, is_active",
                          c=code, n=body.name)
        await audit(db, admin["id"], "sport_added", "sport", row["id"] if row else None, body.name)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise conflict("sport_exists", "Такой вид спорта уже есть") from None
    return row or {}


@router.patch("/admin/sports/{sport_id}")
async def admin_patch_sport(sport_id: int, body: SportPatch, admin: Admin, db: DB) -> dict[str, Any]:
    from sqlalchemy.exc import IntegrityError
    if body.name is not None and not validators.clean_text(body.name, 40, "Название"):
        raise ApiError(422, "validation_error", "Название не может быть пустым")
    try:
        changed = await q_exec(
            db, "UPDATE sports SET name = coalesce(:n, name), is_active = coalesce(:a, is_active) WHERE id = :id",
            n=validators.clean_text(body.name, 40, "Название") if body.name else None, a=body.is_active, id=sport_id)
        if not changed:
            raise not_found("Вид спорта")
        await audit(db, admin["id"], "sport_updated", "sport", sport_id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise conflict("sport_exists", "Такой вид спорта уже есть") from None
    return {"items": await list_sports(db, include_inactive=True)}


# ============================================================================ жалобы
@router.get("/admin/reports")
async def list_reports(reviewer: ReportReviewer, db: DB,
                       status: Literal["open", "resolved", "dismissed"] = "open",
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = await q_all(
        db,
        f"""SELECT r.id, r.reason, r.description, r.status, r.created_at, r.resolved_at, r.resolution_note,
                   {user_json('rp')} AS reporter,
                   CASE WHEN tu.id IS NULL THEN NULL ELSE {user_json('tu')} END AS target_user,
                   r.target_venue_id, tv.name AS target_venue_name, r.target_game_id, tg.title AS target_game_title
            FROM reports r JOIN users rp ON rp.id = r.reporter_id
            LEFT JOIN users tu ON tu.id = r.target_user_id
            LEFT JOIN venues tv ON tv.id = r.target_venue_id
            LEFT JOIN games tg ON tg.id = r.target_game_id
            WHERE r.status = :st ORDER BY r.id DESC LIMIT :limit OFFSET :offset""",
        st=status, limit=limit, offset=offset)
    for r in rows:
        r["reporter"] = public_user(r["reporter"])
        r["target_user"] = public_user(r["target_user"]) if r["target_user"] else None
    return {"items": rows}


class ResolveIn(BaseModel):
    status: Literal["resolved", "dismissed"]
    note: str | None = None

    @field_validator("note")
    @classmethod
    def _n(cls, v: str | None) -> str | None:
        return validators.clean_text(v, 500, "Заметка")


@router.post("/admin/reports/{report_id}/resolve")
async def resolve_report(report_id: int, body: ResolveIn, reviewer: ReportReviewer, db: DB) -> dict[str, Any]:
    r = await q_one(db, "SELECT id, status FROM reports WHERE id = :id FOR UPDATE", id=report_id)
    if r is None:
        raise not_found("Жалоба")
    if r["status"] != "open":
        raise conflict("already_decided", "Жалоба уже рассмотрена")
    await q_exec(db, "UPDATE reports SET status = :s, resolved_by = :u, resolved_at = now(), resolution_note = :n WHERE id = :id",
                 s=body.status, u=reviewer["id"], n=body.note, id=report_id)
    await audit(db, reviewer["id"], "report_" + body.status, "report", report_id)
    await db.commit()
    return {"id": report_id, "status": body.status}


# ============================================================================ аудит и состояние системы
@router.get("/admin/audit")
async def audit_log(admin: Admin, db: DB, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rows = await q_all(
        db,
        """SELECT a.id, a.action, a.target_type, a.target_id, a.details, a.created_at, u.login AS actor_login
           FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.id DESC LIMIT :limit OFFSET :offset""",
        limit=limit, offset=offset)
    return {"items": rows}


@router.get("/admin/system")
async def system_status(request: Request, admin: Admin, db: DB, settings: SettingsDep) -> dict[str, Any]:
    uploads = settings.uploads_path
    total, used, free = shutil.disk_usage(uploads)
    free_gb = free / 1024 ** 3
    warnings: list[str] = []
    if free_gb < settings.min_free_disk_gb:
        warnings.append(f"Мало свободного места на диске: {free_gb:.1f} ГБ (порог {settings.min_free_disk_gb:g} ГБ)")
    if not await check_collation(request.app.state.engine):
        warnings.append("База данных не различает регистр кириллицы: поиск может работать неточно. См. docs/POSTGRESQL.md")
    counts = await q_one(
        db, "SELECT (SELECT count(*) FROM users WHERE deleted_at IS NULL) AS users, "
            "(SELECT count(*) FROM venues WHERE status = 'active') AS venues, "
            "(SELECT count(*) FROM venue_submissions WHERE status = 'pending') AS pending_submissions, "
            "(SELECT count(*) FROM venue_change_proposals WHERE status = 'pending') AS pending_proposals, "
            "(SELECT count(*) FROM reports WHERE status = 'open') AS open_reports, "
            "(SELECT count(*) FROM moderator_requests WHERE status = 'pending') AS pending_moderator_requests")
    return {"disk": {"free_gb": round(free_gb, 2), "total_gb": round(total / 1024 ** 3, 1)},
            "warnings": warnings, "counts": counts}
