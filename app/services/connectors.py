"""数据源连接：SQLite（只读打开）与 MySQL（只读账号 + 超时）。"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ..config import settings


class DataSourceError(RuntimeError):
    pass


def sqlite_path(ds) -> str:
    path = Path(ds.file_path)
    if not path.exists():
        raise DataSourceError(f"数据库文件不存在：{path}")
    return str(path)


def sqlite_connect(ds) -> sqlite3.Connection:
    """只读打开：mode=ro，防止任何写操作。"""
    path = sqlite_path(ds)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = None
    # 排序/分组产生的临时数据放内存：受限环境磁盘不可写时会报 unable to open database file
    try:
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA cache_size=-40000")
    except sqlite3.DatabaseError:
        pass
    return conn


def _sqlite_execute(ds, sql: str, max_rows: int, timeout_s: int) -> tuple[list[str], list[list[Any]]]:
    conn = sqlite_connect(ds)
    deadline = time.time() + timeout_s
    try:
        conn.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 2000)
        cur = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchmany(max_rows + 1)]
        return columns, rows
    finally:
        conn.close()


def _mysql_engine(ds):
    from sqlalchemy import create_engine

    url = f"mysql+pymysql://{ds.username}:{ds.password}@{ds.host}:{ds.port}/{ds.database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def _mysql_execute(ds, sql: str, max_rows: int, timeout_s: int) -> tuple[list[str], list[list[Any]]]:
    from sqlalchemy import text

    engine = _mysql_engine(ds)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={timeout_s * 1000}"))
            except Exception:  # noqa: BLE001  MySQL 5.6 不支持
                pass
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchmany(max_rows + 1)]
            return columns, rows
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(str(exc)) from exc
    finally:
        engine.dispose()


def execute(ds, sql: str, max_rows: int | None = None, timeout_s: int | None = None):
    max_rows = max_rows or settings.max_rows
    timeout_s = timeout_s or settings.query_timeout_seconds
    if ds.kind == "sqlite":
        return _sqlite_execute(ds, sql, max_rows, timeout_s)
    if ds.kind == "mysql":
        return _mysql_execute(ds, sql, max_rows, timeout_s)
    raise DataSourceError(f"不支持的数据源类型：{ds.kind}")


def test_connection(ds) -> tuple[bool, str]:
    try:
        columns, rows = execute(ds, "SELECT 1 AS ok", max_rows=1, timeout_s=20)
        return True, f"连接成功（{columns[0]}={rows[0][0]}）"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:500]
