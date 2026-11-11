"""结果解读：一句话结论 + 图表建议。"""
from __future__ import annotations

import json

from . import llm


def summarize(question: str, columns: list[str], rows: list[list]) -> str:
    if not rows:
        return "查询没有返回数据，可能是筛选条件太严格。"
    sample = [dict(zip(columns, r, strict=False)) for r in rows[:10]]
    prompt = (
        f"用户问题：{question}\n"
        f"查询结果（前 10 行，共 {len(rows)} 行）：{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
        "请用一句中文总结这个结果说明了什么，不超过 40 字，只基于数据，不要编造数字。"
    )
    try:
        text, _ = llm.chat([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=120)
        return text.strip().replace("\n", " ")[:120]
    except Exception:  # noqa: BLE001
        return ""


def suggest_chart(columns: list[str], rows: list[list]) -> dict | None:
    """简单规则：1 个类别列 + 1 个数值列 → 柱状图；两列都是数值 → 折线；否则不出图。"""
    if len(rows) < 2 or len(columns) < 2:
        return None

    def is_number(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    numeric_idx = [i for i in range(len(columns)) if any(is_number(r[i]) for r in rows[:5])]
    text_idx = [i for i in range(len(columns)) if i not in numeric_idx]
    if not numeric_idx:
        return None

    y = columns[numeric_idx[0]]
    if text_idx:
        x = columns[text_idx[0]]
        chart_type = "bar" if len(rows) <= 30 else "line"
        return {"type": chart_type, "x": x, "y": y}
    return {"type": "line", "x": columns[0], "y": y}
