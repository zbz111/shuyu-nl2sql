"""数据源：SQLite 上传 / MySQL 连接、连通性测试、表结构浏览。"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import client_ip, get_current_user
from ..models import AuditLog, DataSource, User
from ..schemas import DataSourceCreate, DataSourceOut, NotesIn, TableInfo
from ..services import connectors, introspection, tabular

router = APIRouter(prefix="/api/v1/datasources", tags=["datasources"])


def _owned(db: Session, ds_id: int, user: User) -> DataSource:
    ds = db.get(DataSource, ds_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if ds.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该数据源")
    return ds


def _to_out(db: Session, ds: DataSource) -> DataSourceOut:
    tables = []
    try:
        tables = json.loads(ds.selected_tables or "[]")
    except json.JSONDecodeError:
        tables = []
    return DataSourceOut(
        id=ds.id,
        name=ds.name,
        kind=ds.kind,
        database=ds.database,
        host=ds.host,
        port=ds.port,
        status=ds.status,
        last_error=ds.last_error,
        selected_tables=tables,
        notes=getattr(ds, "notes", "") or "",
        table_count=len(tables),
        created_at=ds.created_at,
    )


@router.get("", response_model=list[DataSourceOut])
def list_datasources(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(DataSource).order_by(DataSource.id.desc())
    if user.role != "admin":
        stmt = stmt.where(DataSource.owner_id == user.id)
    return [_to_out(db, ds) for ds in db.scalars(stmt).all()]


@router.post("", response_model=DataSourceOut, status_code=status.HTTP_201_CREATED)
def create_datasource(
    body: DataSourceCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.kind not in {"mysql"}:
        raise HTTPException(status_code=400, detail="远程数据源目前只支持 MySQL，SQLite 请用上传")
    ds = DataSource(
        name=body.name.strip(),
        kind="mysql",
        host=body.host.strip(),
        port=body.port,
        database=body.database.strip(),
        username=body.username.strip(),
        password=body.password,
        owner_id=user.id,
        selected_tables="[]",
    )
    ok, msg = connectors.test_connection(ds)
    ds.status = "ok" if ok else "error"
    ds.last_error = "" if ok else msg
    db.add(ds)
    db.commit()
    db.refresh(ds)
    db.add(AuditLog(user_id=user.id, action="datasource_create", target=ds.name, detail=msg, ip=client_ip(request)))
    db.commit()
    return _to_out(db, ds)


@router.post("/upload", response_model=DataSourceOut, status_code=status.HTTP_201_CREATED)
async def upload_sqlite(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = Path(file.filename or "database.db").name
    suffix = Path(name).suffix.lower()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 200MB")

    # ---------- CSV / Excel：自动建表 ----------
    if suffix in {".csv", ".xlsx", ".xlsm"}:
        raw = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
        raw.write_bytes(content)
        db_path = settings.upload_dir / f"{uuid.uuid4().hex}.db"
        try:
            frames, kind = tabular.load_file(raw)
            if kind == "csv":
                # 用文件名当表名，比 "data" 更直观
                frames = {Path(name).stem: next(iter(frames.values()))}
            created = tabular.import_frames(frames, db_path)
        except Exception as exc:  # noqa: BLE001
            raw.unlink(missing_ok=True)
            db_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"导入失败：{exc}") from exc
        finally:
            raw.unlink(missing_ok=True)

        ds = DataSource(
            name=name,
            kind="sqlite",
            file_path=str(db_path),
            owner_id=user.id,
            selected_tables=json.dumps([t["table"] for t in created], ensure_ascii=False),
            status="ok",
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        db.add(
            AuditLog(
                user_id=user.id,
                action="datasource_import",
                target=name,
                detail=json.dumps(created, ensure_ascii=False)[:1500],
                ip=client_ip(request),
            )
        )
        db.commit()
        return _to_out(db, ds)

    # ---------- SQLite 文件 ----------
    if suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise HTTPException(status_code=400, detail="支持 .csv / .xlsx / .db / .sqlite")

    target = settings.upload_dir / f"{uuid.uuid4().hex}.db"
    target.write_bytes(content)

    ds = DataSource(
        name=name,
        kind="sqlite",
        file_path=str(target),
        owner_id=user.id,
        selected_tables="[]",
    )
    ok, msg = connectors.test_connection(ds)
    if not ok:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"不是合法的 SQLite 数据库：{msg}")

    try:
        tables = introspection.list_tables(ds, with_sample=False)
        ds.selected_tables = json.dumps([t["name"] for t in tables], ensure_ascii=False)
    except Exception:  # noqa: BLE001
        ds.selected_tables = "[]"
    ds.status = "ok"
    db.add(ds)
    db.commit()
    db.refresh(ds)
    db.add(AuditLog(user_id=user.id, action="datasource_upload", target=name, ip=client_ip(request)))
    db.commit()
    return _to_out(db, ds)


@router.post("/{ds_id}/test")
def test(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _owned(db, ds_id, user)
    ok, msg = connectors.test_connection(ds)
    ds.status = "ok" if ok else "error"
    ds.last_error = "" if ok else msg
    db.commit()
    return {"ok": ok, "message": msg}


@router.get("/{ds_id}/tables", response_model=list[TableInfo])
def tables(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _owned(db, ds_id, user)
    try:
        data = introspection.list_tables(ds, with_sample=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [TableInfo(**t) for t in data]


@router.put("/{ds_id}/tables")
def save_tables(
    ds_id: int,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ds = _owned(db, ds_id, user)
    names = payload.get("tables") or []
    if not isinstance(names, list):
        raise HTTPException(status_code=400, detail="tables 必须是数组")
    ds.selected_tables = json.dumps(names, ensure_ascii=False)
    db.commit()
    return {"ok": True, "tables": names}


@router.put("/{ds_id}/notes")
def save_notes(
    ds_id: int,
    body: NotesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存业务口径说明，会注入到生成 SQL 的提示里。"""
    ds = _owned(db, ds_id, user)
    ds.notes = (body.notes or "")[:2000]
    db.commit()
    return {"ok": True, "notes": ds.notes}


@router.delete("/{ds_id}")
def delete_datasource(ds_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _owned(db, ds_id, user)
    if ds.kind == "sqlite" and ds.file_path:
        Path(ds.file_path).unlink(missing_ok=True)
    db.delete(ds)
    db.commit()
    return {"ok": True}
