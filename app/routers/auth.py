"""认证接口。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import client_ip, get_current_user
from ..models import AuditLog, User
from ..schemas import LoginRequest, PasswordChange, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        db.add(AuditLog(action="login_failed", target=body.username, ip=client_ip(request)))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    user.last_login_at = datetime.now()
    db.add(AuditLog(user_id=user.id, action="login", target=user.username, ip=client_ip(request)))
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, user.username, user.role),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/change-password")
def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    db.add(AuditLog(user_id=user.id, action="change_password", target=user.username, ip=client_ip(request)))
    db.commit()
    return {"ok": True}
