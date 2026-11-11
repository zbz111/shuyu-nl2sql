"""管理后台：统计、用户、审计。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import client_ip, require_admin
from ..models import AuditLog, DataSource, Query, User
from ..schemas import AuditOut, StatsOut, UserCreate, UserOut
from ..security import hash_password
from ..services import llm

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats", response_model=StatsOut)
def stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    today = datetime.combine(date.today(), datetime.min.time())
    total = db.scalar(select(func.count()).select_from(Query)) or 0
    errors = db.scalar(select(func.count()).select_from(Query).where(Query.status != "ok")) or 0
    return StatsOut(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        datasources=db.scalar(select(func.count()).select_from(DataSource)) or 0,
        queries=total,
        queries_today=db.scalar(select(func.count()).select_from(Query).where(Query.created_at >= today)) or 0,
        error_rate=round(errors / total, 3) if total else 0.0,
        avg_latency_ms=int(db.scalar(select(func.coalesce(func.avg(Query.latency_ms), 0))) or 0),
    )


@router.get("/users", response_model=list[UserOut])
def users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [UserOut.model_validate(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
        role=body.role if body.role in {"admin", "user"} else "user",
    )
    db.add(user)
    db.add(AuditLog(user_id=admin.id, action="user_create", target=user.username, ip=client_ip(request)))
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    is_active: bool | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    return {"ok": True}


@router.get("/logs", response_model=list[AuditOut])
def logs(limit: int = 100, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [AuditOut.model_validate(r) for r in rows]


@router.get("/system")
def system(admin: User = Depends(require_admin)):
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "llm": llm.health(),
        "max_rows": settings.max_rows,
        "timeout": settings.query_timeout_seconds,
        "max_retry": settings.max_retry,
    }
