"""查询：自然语言 → SQL、直接执行 SQL、历史、收藏、会话。"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import client_ip, get_current_user
from ..models import AuditLog, Conversation, DataSource, Query, User
from ..schemas import (
    ConversationOut,
    QueryHistoryItem,
    QueryRequest,
    QueryResult,
    SqlExecuteRequest,
)
from ..services import analytics, connectors, generator, narration, sqlguard

router = APIRouter(tags=["query"])


def _owned_ds(db: Session, ds_id: int, user: User) -> DataSource:
    ds = db.get(DataSource, ds_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if ds.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该数据源")
    return ds


def _ensure_conversation(db: Session, ds_id: int, user_id: int, conv_id: int | None, question: str):
    if conv_id:
        conv = db.get(Conversation, conv_id)
        if conv is None or conv.user_id != user_id or conv.datasource_id != ds_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conv
    conv = Conversation(datasource_id=ds_id, user_id=user_id, title=question[:30] or "新分析")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _history_sql(db: Session, conv_id: int | None) -> str | None:
    if not conv_id:
        return None
    last = db.scalar(
        select(Query).where(Query.conversation_id == conv_id, Query.status == "ok").order_by(Query.id.desc())
    )
    return last.sql if last else None


@router.post("/api/v1/query", response_model=QueryResult)
def query(
    body: QueryRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ds = _owned_ds(db, body.datasource_id, user)
    conv = _ensure_conversation(db, ds.id, user.id, body.conversation_id, body.question)
    history = _history_sql(db, conv.id)

    result = generator.run(ds, body.question, history)

    record = Query(
        conversation_id=conv.id,
        datasource_id=ds.id,
        user_id=user.id,
        question=body.question,
        sql=result["sql"],
        status=result["status"],
        columns_json=json.dumps(result["columns"], ensure_ascii=False),
        rows_json=json.dumps(result["rows"][:200], ensure_ascii=False, default=str),
        row_count=result["row_count"],
        latency_ms=result["latency_ms"],
        error=result["error"],
        retries=result["retries"],
    )
    db.add(record)
    db.add(AuditLog(user_id=user.id, action="query", target=ds.name, detail=body.question[:300], ip=client_ip(request)))
    db.commit()
    db.refresh(record)

    return QueryResult(
        query_id=record.id,
        sql=result["sql"],
        status=result["status"],
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        latency_ms=result["latency_ms"],
        error=result["error"],
        retries=result["retries"],
        chart=result.get("chart"),
        narration=result.get("narration", ""),
        insights=result.get("insights", []),
        insight_summary=result.get("insight_summary", ""),
        hypotheses=result.get("hypotheses", []),
        conversation_id=conv.id,
    )


@router.post("/api/v1/query/execute", response_model=QueryResult)
def execute_sql(
    body: SqlExecuteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ds = _owned_ds(db, body.datasource_id, user)
    started = time.time()
    sql = sqlguard.clean_sql(body.sql)
    try:
        safe_sql = sqlguard.validate(sql, settings.max_rows)
    except sqlguard.SqlRejected as exc:
        return QueryResult(
            query_id=0, sql=sql, status="blocked", error=str(exc), latency_ms=int((time.time() - started) * 1000)
        )

    try:
        columns, rows = connectors.execute(ds, safe_sql, settings.max_rows)
        rows = rows[: settings.max_rows]
        ins = analytics.build_insights(columns, rows)
        result = QueryResult(
            query_id=0,
            sql=safe_sql,
            status="ok",
            columns=columns,
            rows=rows,
            row_count=len(rows),
            latency_ms=int((time.time() - started) * 1000),
            narration=ins["summary"] or narration.summarize("（手动执行）", columns, rows),
            chart=ins["chart_hint"] or narration.suggest_chart(columns, rows),
            insights=ins["facts"],
            insight_summary=ins["summary"],
            hypotheses=analytics.hypotheses(columns, rows, ins),
        )
    except Exception as exc:  # noqa: BLE001
        result = QueryResult(
            query_id=0,
            sql=safe_sql,
            status="error",
            error=str(exc)[:1000],
            latency_ms=int((time.time() - started) * 1000),
        )

    record = Query(
        datasource_id=ds.id,
        user_id=user.id,
        question="（手动执行 SQL）",
        sql=safe_sql,
        status=result.status,
        columns_json=json.dumps(result.columns, ensure_ascii=False),
        rows_json=json.dumps(result.rows[:200], ensure_ascii=False, default=str),
        row_count=result.row_count,
        latency_ms=result.latency_ms,
        error=result.error,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result.query_id = record.id
    return result


@router.get("/api/v1/queries", response_model=list[QueryHistoryItem])
def history(
    datasource_id: int | None = None,
    favorite: bool = False,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Query).where(Query.user_id == user.id).order_by(Query.id.desc()).limit(min(limit, 200))
    if datasource_id:
        stmt = stmt.where(Query.datasource_id == datasource_id)
    if favorite:
        stmt = stmt.where(Query.favorite.is_(True))
    return [
        QueryHistoryItem(
            id=q.id,
            question=q.question,
            sql=q.sql,
            status=q.status,
            row_count=q.row_count,
            latency_ms=q.latency_ms,
            favorite=q.favorite,
            created_at=q.created_at,
        )
        for q in db.scalars(stmt).all()
    ]


@router.post("/api/v1/queries/{query_id}/favorite")
def toggle_favorite(query_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.get(Query, query_id)
    if q is None or (q.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="记录不存在")
    q.favorite = not q.favorite
    db.commit()
    return {"favorite": q.favorite}


@router.get("/api/v1/conversations", response_model=list[ConversationOut])
def conversations(
    datasource_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(100)
    if datasource_id:
        stmt = stmt.where(Conversation.datasource_id == datasource_id)
    return [
        ConversationOut(id=c.id, datasource_id=c.datasource_id, title=c.title, updated_at=c.updated_at)
        for c in db.scalars(stmt).all()
    ]


@router.get("/api/v1/conversations/{conv_id}/queries", response_model=list[QueryResult])
def conversation_queries(
    conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = db.scalars(select(Query).where(Query.conversation_id == conv_id).order_by(Query.id)).all()
    out = []
    for q in rows:
        out.append(
            QueryResult(
                query_id=q.id,
                sql=q.sql,
                status=q.status,
                columns=json.loads(q.columns_json or "[]"),
                rows=json.loads(q.rows_json or "[]"),
                row_count=q.row_count,
                latency_ms=q.latency_ms,
                error=q.error,
                retries=q.retries,
                narration="",
                chart=None,
                conversation_id=conv_id,
            )
        )
    return out


@router.delete("/api/v1/conversations/{conv_id}")
def delete_conversation(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(conv)
    db.commit()
    return {"ok": True}
