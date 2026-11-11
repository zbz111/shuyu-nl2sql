"""表结构内省：表、字段、行数、示例数据，并生成给模型看的 DDL。"""
from __future__ import annotations

import sqlite3

from ..config import settings
from . import connectors


def _sqlite_tables(ds) -> list[str]:
    conn = connectors.sqlite_connect(ds)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str, bool, bool]]:
    """返回 (列名, 类型, 是否非空, 是否主键)。

    PRAGMA table_info 的字段顺序是 cid, name, type, notnull, dflt_value, pk。
    之前误把 notnull 当成 pk，导致建表语句里所有非空列都被标成 PRIMARY KEY，
    会误导模型以为这些列唯一，进而写出错误的去重/聚合逻辑。
    """
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return [(r[1], r[2] or "TEXT", bool(r[3]), bool(r[5])) for r in rows]


def list_tables(ds, with_sample: bool = True) -> list[dict]:
    if ds.kind == "sqlite":
        conn = connectors.sqlite_connect(ds)
        try:
            tables = _sqlite_tables(ds)
            out = []
            for name in tables:
                cols = _sqlite_columns(conn, name)
                try:
                    count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                except Exception:  # noqa: BLE001
                    count = 0
                sample = []
                if with_sample:
                    try:
                        cur = conn.execute(f'SELECT * FROM "{name}" LIMIT {settings.schema_sample_rows}')
                        colnames = [d[0] for d in cur.description]
                        sample = [dict(zip(colnames, r, strict=False)) for r in cur.fetchall()]
                    except Exception:  # noqa: BLE001
                        sample = []
                out.append(
                    {
                        "name": name,
                        "columns": [
                            {
                                "name": c[0],
                                "type": c[1],
                                "notnull": c[2],
                                "pk": c[3],
                            }
                            for c in cols
                        ],
                        "row_count": count,
                        "sample": sample,
                    }
                )
            return out
        finally:
            conn.close()

    # MySQL：用 SQLAlchemy inspector
    from sqlalchemy import inspect, text

    engine = connectors._mysql_engine(ds)  # noqa: SLF001
    try:
        inspector = inspect(engine)
        out = []
        for name in inspector.get_table_names():
            cols = [{"name": c["name"], "type": str(c["type"]), "pk": bool(c.get("primary_key"))} for c in inspector.get_columns(name)]
            count = 0
            sample = []
            with engine.connect() as conn:
                try:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar() or 0
                    if with_sample:
                        res = conn.execute(text(f"SELECT * FROM `{name}` LIMIT {settings.schema_sample_rows}"))
                        keys = list(res.keys())
                        sample = [dict(zip(keys, r, strict=False)) for r in res.fetchall()]
                except Exception:  # noqa: BLE001
                    pass
            out.append({"name": name, "columns": cols, "row_count": count, "sample": sample})
        return out
    finally:
        engine.dispose()


def schema_ddl(ds, table_names: list[str] | None = None, include_sample: bool = True) -> str:
    """生成给模型看的 schema：建表语句 + 行数 + 少量示例数据。"""
    tables = list_tables(ds, with_sample=include_sample)
    if table_names:
        wanted = set(table_names)
        tables = [t for t in tables if t["name"] in wanted]

    blocks: list[str] = []
    for t in tables:
        cols = []
        for c in t["columns"]:
            cols.append(f"  {c['name']} {c['type']}" + (" PRIMARY KEY" if c.get("pk") else ""))
        block = f"CREATE TABLE {t['name']} (\n" + ",\n".join(cols) + "\n);"
        block += f"\n-- 行数：{t['row_count']}"
        if include_sample and t["sample"]:
            block += f"\n-- 示例：{t['sample'][:2]}"
        blocks.append(block)
    return "\n\n".join(blocks)


def pick_tables(ds, question: str, max_tables: int = 12) -> list[str]:
    """表多时做一次粗筛：表名/字段名与问题关键词的重合度。"""
    tables = list_tables(ds, with_sample=False)
    if len(tables) <= max_tables:
        return [t["name"] for t in tables]

    q = question.lower()
    scored: list[tuple[int, str]] = []
    for t in tables:
        score = 0
        if t["name"].lower() in q:
            score += 5
        for c in t["columns"]:
            if c["name"].lower() in q:
                score += 1
        scored.append((score, t["name"]))
    scored.sort(reverse=True)
    return [name for _, name in scored[:max_tables]]
