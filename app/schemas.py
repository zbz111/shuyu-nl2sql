"""请求 / 响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool = True

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""
    role: str = "user"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------- 数据源 ----------
class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = "sqlite"  # sqlite | mysql
    host: str = "127.0.0.1"
    port: int = 3306
    database: str = ""
    username: str = ""
    password: str = ""
    notes: str = ""


class DataSourceOut(BaseModel):
    id: int
    name: str
    kind: str
    database: str = ""
    host: str = ""
    port: int = 0
    status: str = "unknown"
    last_error: str = ""
    selected_tables: list[str] = []
    notes: str = ""
    table_count: int = 0
    created_at: datetime | None = None


class NotesIn(BaseModel):
    notes: str = ""


class TableInfo(BaseModel):
    name: str
    columns: list[dict] = []
    row_count: int = 0
    sample: list[dict] = []


# ---------- 查询 ----------
class QueryRequest(BaseModel):
    datasource_id: int
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None


class SqlExecuteRequest(BaseModel):
    datasource_id: int
    sql: str


class QueryResult(BaseModel):
    query_id: int
    sql: str
    status: str
    columns: list[str] = []
    rows: list[list] = []
    row_count: int = 0
    latency_ms: int = 0
    error: str = ""
    retries: int = 0
    chart: dict | None = None
    narration: str = ""
    insights: list[dict] = []
    insight_summary: str = ""
    hypotheses: list[str] = []
    conversation_id: int | None = None


class QueryHistoryItem(BaseModel):
    id: int
    question: str
    sql: str = ""
    status: str
    row_count: int = 0
    latency_ms: int = 0
    favorite: bool = False
    created_at: datetime | None = None


class ConversationOut(BaseModel):
    id: int
    datasource_id: int
    title: str
    updated_at: datetime | None = None


# ---------- 管理 ----------
class StatsOut(BaseModel):
    users: int
    datasources: int
    queries: int
    queries_today: int
    error_rate: float
    avg_latency_ms: int


class AuditOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    target: str
    detail: str
    ip: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
