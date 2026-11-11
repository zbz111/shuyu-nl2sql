"""Text2SQL：Prompt 编排、生成、校验、执行、失败重试。"""
from __future__ import annotations

import time

from ..config import settings
from . import analytics, connectors, introspection, llm, narration, sqlguard

SYSTEM = """你是资深的 SQLite/MySQL 数据分析师。把用户的中文问题翻译成一条 SQL。

硬性规则：
1. 只输出 SQL，不要解释，不要 markdown 代码块。
2. 只能写 SELECT（可用 WITH），禁止任何写操作。
3. 表名、字段名必须来自给定的表结构，禁止臆造。
4. 中文取值（如城市名、品类名）直接用字符串精确匹配，不要用拼音或英文。
5. 日期字段是 TEXT（格式 YYYY-MM-DD），按月统计用 substr(date, 1, 7)。
6. 结果集不要超过 500 行，必要时加 LIMIT。
7. 列名用中文别名（AS "销售额"），方便直接展示。
8. 只能输出**一条** SQL；若需要多个结果，用 UNION ALL 或子查询合并成一条，禁止输出多条语句。
9. 问“走势 / 每天 / 每月 / 变化”时，返回按时间升序的**完整序列**，不要只返回最大或最小值。
10. 问“A 比 B 高多少”时：返回按维度分组的明细行（如按月、按日号分组），不要只算出一个差值。
    问“为什么 A 比 B 多”时：返回能支撑归因的**更大范围明细**（例如按日号分组的全部月份数据），
    不要只返回被比较的那两个点。
11. 只有当用户明确只要一个数（如“总共多少”）时，才返回单个汇总值。
12. 按“日号”（几号）分析时用 substr(日期, 9, 2) 取日号并 GROUP BY。
13. 区分口径：“销量/数量/件数”用 quantity、total_qty；“销售额/金额/营收/GMV”用 revenue、total_revenue。
    两者不可混用——问销量就必须按数量排序，不能按金额排序。
14. 排序类问题（最高、最多、TopN）必须把**排序依据的数值列**和名称一起返回，
    例如 SELECT description AS 产品, SUM(quantity) AS 销量 ... ORDER BY 销量 DESC LIMIT 5。

示例（务必照此思路）：
问题：1 号为什么比 5 号卖得多？
正确 SQL：SELECT substr(日期,9,2) AS "日号", AVG(销售额) AS "平均销售额" FROM 日销售数据 GROUP BY "日号" ORDER BY "日号"
错误 SQL：WHERE 日期 IN ('2026-07-01','2026-07-05')  ← 只取两个点，无法归因

问题：8 月比 7 月卖得好吗？
正确 SQL：SELECT substr(日期,1,7) AS "月份", SUM(销售额) AS "销售额" FROM 日销售数据 GROUP BY "月份" ORDER BY "月份"
错误 SQL：直接算出差值只返回一个数  ← 没有对比结构
"""


def build_prompt(question: str, ddl: str, history_sql: str | None = None, notes: str = "") -> str:
    parts: list[str] = []
    if notes and notes.strip():
        parts.append(f"【业务说明（口径以此为准）】\n{notes.strip()}")
    parts.append(f"【表结构】\n{ddl}")
    parts.append(f"【问题】\n{question}")
    if history_sql:
        parts.append(f"【上一轮 SQL（用户可能在此基础上追问）】\n{history_sql}")
    parts.append("输出一条 SQL：")
    return "\n\n".join(parts)


def generate(question: str, ddl: str, history_sql: str | None = None, notes: str = "") -> tuple[str, int]:
    raw, tokens = llm.chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(question, ddl, history_sql, notes)},
        ],
        temperature=0,
        max_tokens=500,
    )
    return sqlguard.clean_sql(raw), tokens


def fix(question: str, ddl: str, bad_sql: str, error: str, notes: str = "") -> str:
    head = f"【业务说明（口径以此为准）】\n{notes.strip()}\n\n" if notes and notes.strip() else ""
    prompt = (
        f"{head}【表结构】\n{ddl}\n\n【问题】\n{question}\n\n"
        f"【错误的 SQL】\n{bad_sql}\n\n【数据库报错】\n{error}\n\n"
        "请修正后只输出一条 SQL："
    )
    raw, _ = llm.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=500,
    )
    return sqlguard.clean_sql(raw)


def run(ds, question: str, history_sql: str | None = None) -> dict:
    """完整流程：选表 → 生成 → 校验 → 执行 → 失败重试 → 结论与图表建议。"""
    started = time.time()

    def _fail(message: str) -> dict:
        return {
            "sql": "",
            "status": "error",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": message,
            "retries": 0,
            "latency_ms": int((time.time() - started) * 1000),
            "tokens": 0,
            "narration": "",
            "chart": None,
        }

    try:
        tables = introspection.pick_tables(ds, question)
        ddl = introspection.schema_ddl(ds, tables)
        notes = getattr(ds, "notes", "") or ""
        sql, tokens = generate(question, ddl, history_sql, notes)
    except llm.LLMError as exc:
        return _fail(str(exc))
    except Exception as exc:  # noqa: BLE001  数据库结构读取失败等
        return _fail(f"读取表结构失败：{exc}")

    retries = 0
    last_error = ""

    for attempt in range(settings.max_retry + 1):
        try:
            sql = sqlguard.validate(sql, settings.max_rows)
        except sqlguard.SqlRejected as exc:
            return {
                "sql": sql,
                "status": "blocked",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(exc),
                "retries": retries,
                "latency_ms": int((time.time() - started) * 1000),
                "tokens": tokens,
                "narration": "",
                "chart": None,
            }

        try:
            columns, rows = connectors.execute(ds, sql, settings.max_rows)
            truncated = len(rows) > settings.max_rows
            rows = rows[: settings.max_rows]
            result = {
                "sql": sql,
                "status": "ok",
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
                "error": "",
                "retries": retries,
                "latency_ms": int((time.time() - started) * 1000),
                "tokens": tokens,
            }
            # 先算事实，再谈表达：数字全部来自 analytics，不经过模型
            ins = analytics.build_insights(columns, rows, question)
            result["insight_summary"] = ins["summary"]
            result["insights"] = ins["facts"]
            result["hypotheses"] = analytics.hypotheses(columns, rows, ins, question=question)
            result["chart"] = ins["chart_hint"] or narration.suggest_chart(columns, rows)
            # 有确定性结论就用它；否则退回模型概述
            result["narration"] = ins["summary"] or narration.summarize(question, columns, rows)
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= settings.max_retry:
                break
            retries += 1
            try:
                sql = fix(question, ddl, sql, last_error, notes)
            except llm.LLMError as fix_exc:
                last_error = f"{last_error}（自动修正失败：{fix_exc}）"
                break

    return {
        "sql": sql,
        "status": "error",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": last_error[:1000],
        "retries": retries,
        "latency_ms": int((time.time() - started) * 1000),
        "tokens": tokens,
        "narration": "",
        "chart": None,
    }
