"""SQL 安全：单语句、只读、危险关键字拦截、强制行数上限。"""
from __future__ import annotations

import re

import sqlparse

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "truncate", "grant", "revoke", "attach", "detach", "pragma",
    "load_file", "outfile", "dumpfile", "into",
}

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


class SqlRejected(RuntimeError):
    pass


def clean_sql(raw: str) -> str:
    """去掉 markdown 代码块、多余空白、结尾分号。"""
    text = _FENCE.sub("", raw or "").strip()
    text = text.strip().strip("`").strip()
    if text.lower().startswith("sql"):
        text = text[3:].lstrip(": \n")
    return text.rstrip(";").strip()


def validate(sql: str, max_rows: int) -> str:
    if not sql or not sql.strip():
        raise SqlRejected("生成的 SQL 为空")

    statements = [s for s in sqlparse.split(sql) if s.strip()]
    if len(statements) != 1:
        raise SqlRejected("只允许执行单条 SQL")

    stmt = statements[0].strip().rstrip(";")
    lowered = stmt.lower()

    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SqlRejected("只允许 SELECT 查询")

    tokens = {t.value.lower() for t in sqlparse.parse(stmt)[0].flatten()}
    hits = tokens & FORBIDDEN
    if hits:
        raise SqlRejected(f"SQL 包含被禁止的关键字：{', '.join(sorted(hits))}")

    if not re.search(r"\blimit\s+\d+", lowered):
        stmt = f"{stmt}\nLIMIT {max_rows}"

    return stmt


def is_read_only(sql: str) -> bool:
    try:
        validate(sql, 500)
        return True
    except SqlRejected:
        return False
