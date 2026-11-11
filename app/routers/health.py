"""健康检查。"""
from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..services import llm

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok", "version": settings.app_version}


@router.get("/readyz")
def readyz():
    info = llm.health()
    return {"ready": bool(info.get("ok")), "llm": info}
