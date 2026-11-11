"""FastAPI 入口。"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_db
from .models import User
from .routers import admin, auth, datasources, health, query
from .security import hash_password
from .services import llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="自然语言数据分析 Agent：连库、生成 SQL、执行、出图、给结论。",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.time()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    if not request.url.path.startswith(("/assets", "/static")):
        logger.info(
            "%s %s %s %sms id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.time() - started) * 1000),
            rid,
        )
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(datasources.router)
app.include_router(query.router)
app.include_router(admin.router)

STATIC_DIR = Path(__file__).parent / "static"
ASSETS_DIR = STATIC_DIR / "assets"
if ASSETS_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"message": "前端未构建", "api_docs": "/api/docs"})


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith(("api/", "assets/", "healthz", "readyz")):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == settings.admin_username)) is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    display_name="管理员",
                    role="admin",
                )
            )
            db.commit()
            logger.warning("已创建默认管理员 %s / %s —— 请登录后修改", settings.admin_username, settings.admin_password)
    info = llm.health()
    logger.info("模型服务 provider=%s ok=%s model=%s", info.get("provider"), info.get("ok"), info.get("model"))
    if not info.get("ok"):
        logger.warning("模型服务不可达，请检查 Ollama 是否启动")
