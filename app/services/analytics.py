"""数据洞察引擎：从查询结果里算出"发生了什么、为什么"。

设计原则（面试可讲）：
1. **数字全部由代码计算**，模型只负责组织语言 → 不会出现编造的增长率；
2. 每条结论都可追溯到具体列与具体行，前端能高亮对应位置；
3. "原因"分两层：**可证实的相关性**（哪天是周末/月初、环比、集中度）与
   **待核实假设**（模型基于模式提出的猜测，明确标注"推测"）。
"""
from __future__ import annotations

import math
import re
import statistics
from datetime import datetime
from typing import Any

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 类型识别
def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(v)


def _parse_date(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y-%m", "%Y%m%d"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    return None


def classify(columns: list[str], rows: list[list]) -> dict:
    """把列分成 数值 / 日期 / 类别 三类。"""
    if not rows:
        return {"numeric": [], "date": [], "text": []}
    numeric, date, text = [], [], []
    for i, name in enumerate(columns):
        vals = [r[i] for r in rows if r[i] is not None]
        if not vals:
            text.append(i)
            continue
        if sum(1 for v in vals if _is_number(v)) >= max(1, int(len(vals) * 0.9)):
            numeric.append(i)
            continue
        if sum(1 for v in vals if _parse_date(v) is not None) >= max(1, int(len(vals) * 0.9)):
            date.append(i)
            continue
        text.append(i)
    return {"numeric": numeric, "date": date, "text": text}


# ---------------------------------------------------------------- 指标计算
def _fmt(v: float) -> str:
    if abs(v) >= 10000:
        return f"{v:,.0f}"
    if abs(v) >= 100:
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _pct(a: float, b: float) -> str:
    if b == 0:
        return "—"
    return f"{(a - b) / abs(b) * 100:+.1f}%"


def _looks_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _series_stats(labels: list[str], values: list[float]) -> dict:
    peak_i = max(range(len(values)), key=lambda i: values[i])
    low_i = min(range(len(values)), key=lambda i: values[i])
    total = sum(values)
    avg = total / len(values)
    return {
        "peak": {"label": labels[peak_i], "value": values[peak_i], "index": peak_i},
        "trough": {"label": labels[low_i], "value": values[low_i], "index": low_i},
        "total": total,
        "avg": avg,
        "count": len(values),
        "spread_pct": (values[peak_i] - values[low_i]) / abs(avg) * 100 if avg else 0.0,
    }


def _weekday_effect(points: list[tuple[datetime, str, float]]) -> dict | None:
    """按星期几分组，看不同星期几的平均值差异（需要至少 14 天数据）。"""
    if len(points) < 14:
        return None
    buckets: dict[int, list[float]] = {}
    for d, _raw, v in points:
        buckets.setdefault(d.weekday(), []).append(v)
    if len(buckets) < 5:
        return None
    means = {k: statistics.fmean(v) for k, v in buckets.items() if len(v) >= 2}
    if len(means) < 5:
        return None
    overall = statistics.fmean([m for m in means.values()])
    best = max(means, key=means.get)
    worst = min(means, key=means.get)
    return {
        "overall": overall,
        "best_day": best,
        "best_mean": means[best],
        "worst_day": worst,
        "worst_mean": means[worst],
        "by_day": means,
        "gap_pct": (means[best] - means[worst]) / abs(overall) * 100 if overall else 0.0,
    }


def _month_start_effect(points: list[tuple[datetime, str, float]]) -> dict | None:
    """按月内日号分组（需跨至少 2 个月），回答"1 号为什么比 5 号高"。"""
    months = {(d.year, d.month) for d, _raw, _v in points}
    if len(months) < 2:
        return None
    by_day: dict[int, list[float]] = {}
    for d, _raw, v in points:
        by_day.setdefault(d.day, []).append(v)
    means = {k: statistics.fmean(v) for k, v in by_day.items() if len(v) >= 2}
    if len(means) < 5:
        return None
    best = max(means, key=means.get)
    worst = min(means, key=means.get)
    overall = statistics.fmean(means.values())
    return {
        "best_dom": best,
        "best_mean": means[best],
        "worst_dom": worst,
        "worst_mean": means[worst],
        "by_dom": means,
        "gap_pct": (means[best] - means[worst]) / abs(overall) * 100 if overall else 0.0,
    }


def _trend(values: list[float]) -> dict:
    n = len(values)
    if n < 3:
        return {"direction": "flat", "change_pct": 0.0}
    first_half = statistics.fmean(values[: n // 2])
    second_half = statistics.fmean(values[n // 2 :])
    chg = (second_half - first_half) / abs(first_half) * 100 if first_half else 0.0
    direction = "up" if chg > 3 else "down" if chg < -3 else "flat"
    return {"direction": direction, "change_pct": chg, "first_half": first_half, "second_half": second_half}


def _concentration(labels: list[str], values: list[float]) -> dict | None:
    if len(values) < 3:
        return None
    total = sum(values)
    if total == 0:
        return None
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    top1 = values[order[0]] / total
    top3 = sum(values[i] for i in order[:3]) / total
    return {
        "top1_label": labels[order[0]],
        "top1_share": top1,
        "top3_share": top3,
        "bottom_label": labels[order[-1]],
        "bottom_share": values[order[-1]] / total,
    }


# ---------------------------------------------------------------- 问题对齐
def extract_focus(question: str | None, labels: list[str]) -> list[int]:
    """从问题里找出用户想比较的对象，返回其在 labels 中的下标。

    支持："1号/1 号"、"14日"、"2026-07"、"数码/生活"等。
    只在确实能在结果里找到时才返回，避免瞎猜。
    """
    if not question:
        return []
    norm_labels = [re.sub(r"\s+", "", str(x)) for x in labels]
    found: list[int] = []

    # 1) 形如 "1号 / 5 日 / 31号"
    for num in re.findall(r"(\d{1,2})\s*[号日]", question):
        target = f"{int(num)}号"
        for i, lab in enumerate(norm_labels):
            if lab in {target, f"{int(num)}日", str(int(num))} and i not in found:
                found.append(i)
                break

    # 2) 形如 "2026-08"、"8月"
    if not found:
        for ym in re.findall(r"(\d{4}-\d{1,2})", question):
            for i, lab in enumerate(norm_labels):
                if lab == ym.replace("-0", "-").replace("-", "-") or lab == ym:
                    if i not in found:
                        found.append(i)
                        break
        for m in re.findall(r"(\d{1,2})\s*月", question):
            key = f"-{int(m):02d}"
            for i, lab in enumerate(norm_labels):
                if lab.endswith(key) and i not in found:
                    found.append(i)
                    break

    # 3) 类别名直接出现在问题里（取最长匹配，避免"数码"命中"数码配件"两次）
    if not found:
        for kw in sorted({str(x) for x in labels}, key=len, reverse=True):
            k = re.sub(r"\s+", "", kw)
            if len(k) >= 2 and k in question and norm_labels.index(k) not in found:
                found.append(norm_labels.index(k))

    return found[:2]


def _position_hint(label: str) -> str:
    """按日号给一个粗粒度位置描述，用于解释波动（属于推测）。"""
    m = re.match(r"(\d{1,2})", re.sub(r"\s+", "", label))
    if not m:
        return ""
    day = int(m.group(1))
    if day <= 3:
        return "月初"
    if day <= 10:
        return "上旬"
    if day <= 20:
        return "中旬"
    return "下旬"


def compare_focus(labels: list[str], values: list[float], focus: list[int]) -> dict | None:
    """对比用户关心的两个（或多个）对象，输出差额、占比、排名。"""
    if len(focus) < 2:
        return None
    total = sum(values)
    avg = total / len(values) if values else 0.0
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    rank = {idx: pos + 1 for pos, idx in enumerate(order)}

    a, b = focus[0], focus[1]
    va, vb = values[a], values[b]
    diff = va - vb
    diff_pct = (diff / abs(vb) * 100) if vb else 0.0
    ratio = (va / vb) if vb else 0.0

    la, lb = labels[a], labels[b]
    parts = [
        f"{la} 为 {_fmt(va)}（在 {len(values)} 项中排第 {rank[a]}，"
        f"{'高于' if va >= avg else '低于'}均值 {abs(va - avg) / abs(avg) * 100 if avg else 0:.0f}%）；"
        f"{lb} 为 {_fmt(vb)}（排第 {rank[b]}）。"
    ]
    if vb:
        parts.append(f"{la} 比 {lb} {'高' if diff >= 0 else '低'} {abs(diff_pct):.0f}%，相差 {_fmt(abs(diff))}。")

    pa, pb = _position_hint(la), _position_hint(lb)
    if pa and pb and pa != pb:
        parts.append(f"从位置看，{la}属于{pa}，{lb}属于{pb}。")

    return {
        "pair": (la, lb),
        "text": "".join(parts),
        "diff_pct": diff_pct,
        "ratio": ratio,
        "position": (pa, pb),
    }


# ---------------------------------------------------------------- 主入口
def build_insights(columns: list[str], rows: list[list], question: str | None = None) -> dict:
    """返回 {summary, facts, chart_hint, points}。

    question 用于"问题对齐"：问"A 比 B"时优先输出 A 与 B 的对比，
    而不是只给全局峰谷（否则答非所问）。
    """
    if not rows:
        return {"summary": "查询没有返回数据，可能是筛选条件太严格。", "facts": [], "chart_hint": None, "points": []}

    kinds = classify(columns, rows)
    facts: list[dict] = []

    # 数值列：取第一个作为主指标
    if not kinds["numeric"]:
        return {
            "summary": f"共返回 {len(rows)} 行数据，但没有可汇总的数值列。",
            "facts": [],
            "chart_hint": None,
            "points": [],
        }
    y_idx = kinds["numeric"][0]
    y_name = columns[y_idx]
    points = [(i, float(r[y_idx])) for i, r in enumerate(rows) if _is_number(r[y_idx])]

    # 单行结果：直接按"标签：数值"说清楚，不要套用峰谷模板
    if len(rows) == 1:
        cells = [("" if v is None else str(v).strip()) for v in rows[0]]
        texts = [cells[i] for i in range(len(cells)) if i not in kinds["numeric"] and cells[i]]
        nums = [cells[i] for i in range(len(cells)) if i in kinds["numeric"]]
        if nums:
            head = "、".join(texts[:2])
            body = "、".join(_fmt(float(x)) if _looks_number(x) else x for x in nums[:2])
            # 问的是比例/占比时补上百分号，避免出现"结果：84.61"这种半截话
            if len(nums) == 1 and question and re.search(r"占比|比例|百分比|率|%", question):
                body = f"{body}%"
            summary = f"{head}：{body}。" if head else f"结果：{body}。"
            facts = [
                {
                    "type": "scalar",
                    "title": "结果",
                    "text": " ｜ ".join(f"{columns[i]}={cells[i]}" for i in range(len(cells))),
                }
            ]
            return {"summary": summary, "facts": facts, "chart_hint": None, "points": []}

    chart_hint = None
    summary_parts: list[str] = []

    # ---------- 场景 1：日期 + 数值（趋势/峰谷/星期效应）----------
    if kinds["date"]:
        d_idx = kinds["date"][0]
        series: list[tuple[datetime, str, float]] = []
        for r in rows:
            raw = r[d_idx]
            d = _parse_date(raw)
            if d is not None and _is_number(r[y_idx]):
                series.append((d, str(raw), float(r[y_idx])))
        series.sort(key=lambda x: x[0])

        if len(series) >= 2:
            # 标签：YYYY-MM 保留"年月"，YYYY-MM-DD 显示"月-日"，避免把月份显示成 08-01
            labels = []
            for d, raw, _ in series:
                if re.fullmatch(r"\d{4}-\d{2}", raw.strip()):
                    labels.append(raw.strip())
                elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
                    labels.append(d.strftime("%m-%d"))
                else:
                    labels.append(d.strftime("%Y-%m-%d"))
            values = [v for _, _, v in series]
            st = _series_stats(labels, values)

            # 先对齐用户问题：问"A 比 B"就优先比 A 和 B
            focus = extract_focus(question, labels)
            cmp = compare_focus(labels, values, focus)
            if cmp:
                facts.append({"type": "compare", "title": "直接对比", "text": cmp["text"]})
                summary_parts.append(
                    f"{cmp['pair'][0]} 比 {cmp['pair'][1]}"
                    f"{'高' if cmp['diff_pct'] >= 0 else '低'} {abs(cmp['diff_pct']):.0f}%"
                )

            facts.append(
                {
                    "type": "peak_trough",
                    "title": "最高 / 最低",
                    "text": (
                        f"{st['peak']['label']} 最高（{_fmt(st['peak']['value'])}），"
                        f"{st['trough']['label']} 最低（{_fmt(st['trough']['value'])}），"
                        f"峰谷差 {st['spread_pct']:.0f}%（相对均值 {_fmt(st['avg'])}）。"
                    ),
                    "highlight": {"peak_index": st["peak"]["index"], "trough_index": st["trough"]["index"]},
                }
            )
            summary_parts.append(
                f"{st['peak']['label']} {y_name}最高（{_fmt(st['peak']['value'])}），"
                f"{st['trough']['label']} 最低（{_fmt(st['trough']['value'])}），相差 {st['spread_pct']:.0f}%"
            )

            # 相邻点最大波动（回答"1 号到 5 号跌了多少"）
            if len(series) >= 3:
                drops = [
                    (series[i - 1][0], series[i][0], values[i - 1], values[i])
                    for i in range(1, len(values))
                    if values[i - 1] != 0
                ]
                if drops:
                    d_prev, d_cur, v_prev, v_cur = min(drops, key=lambda x: (x[3] - x[2]) / abs(x[2]))
                    drop_pct = (v_cur - v_prev) / abs(v_prev) * 100
                    if drop_pct < -10:
                        facts.append(
                            {
                                "type": "drop",
                                "title": "最大单期下滑",
                                "text": (
                                    f"{d_prev.strftime('%m-%d')} 到 {d_cur.strftime('%m-%d')}，"
                                    f"{y_name}从 {_fmt(v_prev)} 降到 {_fmt(v_cur)}（{drop_pct:+.1f}%）。"
                                ),
                            }
                        )

            tr = _trend(values)
            if tr["direction"] != "flat":
                word = "上升" if tr["direction"] == "up" else "下降"
                facts.append(
                    {
                        "type": "trend",
                        "title": "整体趋势",
                        "text": (
                            f"后半段均值比前半段{word} {abs(tr['change_pct']):.1f}%"
                            f"（{_fmt(tr['first_half'])} → {_fmt(tr['second_half'])}）。"
                        ),
                    }
                )

            wk = _weekday_effect(series)
            if wk:
                best_name = WEEKDAY_CN[wk["best_day"]]
                worst_name = WEEKDAY_CN[wk["worst_day"]]
                facts.append(
                    {
                        "type": "weekday",
                        "title": "星期效应",
                        "text": (
                            f"{best_name}平均最高（{_fmt(wk['best_mean'])}），"
                            f"{worst_name}平均最低（{_fmt(wk['worst_mean'])}），"
                            f"差 {wk['gap_pct']:.0f}%；说明存在明显的周内波动。"
                        ),
                    }
                )
                summary_parts.append(f"{worst_name}通常是低谷，{best_name}通常最好")

            dom = _month_start_effect(series)
            if dom:
                facts.append(
                    {
                        "type": "day_of_month",
                        "title": "月初效应",
                        "text": (
                            f"按月份内的日号看：{dom['best_dom']} 号平均最高（{_fmt(dom['best_mean'])}），"
                            f"{dom['worst_dom']} 号平均最低（{_fmt(dom['worst_mean'])}），"
                            f"差 {dom['gap_pct']:.0f}%。"
                        ),
                    }
                )
                summary_parts.append(
                    f"跨月看，{dom['best_dom']} 号平均高于 {dom['worst_dom']} 号"
                )

            chart_hint = {
                "type": "line" if len(series) > 30 else "bar",
                "x": columns[d_idx],
                "y": y_name,
                "labels": labels,
                "values": values,
                "mark_peak": st["peak"]["index"],
                "mark_trough": st["trough"]["index"],
            }

    # ---------- 场景 2：类别 + 数值（集中度/头部）----------
    elif kinds["text"]:
        c_idx = kinds["text"][0]
        raw_labels = [str(r[c_idx]) for r in rows]
        # 纯 1~2 位数字的标签视为"日号"，加个"号"字更易读
        if raw_labels and all(re.fullmatch(r"\d{1,2}", x or "") for x in raw_labels):
            labels = [f"{int(x)} 号" for x in raw_labels]
        else:
            labels = raw_labels
        values = [float(r[y_idx]) if _is_number(r[y_idx]) else 0.0 for r in rows]
        st = _series_stats(labels, values)
        conc = _concentration(labels, values)

        # 先对齐用户问题：问"A 比 B"就优先比 A 和 B
        focus = extract_focus(question, labels)
        cmp = compare_focus(labels, values, focus)
        if cmp:
            facts.append({"type": "compare", "title": "直接对比", "text": cmp["text"]})
            summary_parts.append(
                f"{cmp['pair'][0]} 比 {cmp['pair'][1]}"
                f"{'高' if cmp['diff_pct'] >= 0 else '低'} {abs(cmp['diff_pct']):.0f}%"
            )

        facts.append(
            {
                "type": "peak_trough",
                "title": "最高 / 最低",
                "text": (
                    f"{st['peak']['label']} 最高（{_fmt(st['peak']['value'])}），"
                    f"{st['trough']['label']} 最低（{_fmt(st['trough']['value'])}），"
                    f"两者相差 {st['spread_pct']:.0f}%。"
                ),
                "highlight": {"peak_index": st["peak"]["index"], "trough_index": st["trough"]["index"]},
            }
        )
        summary_parts.append(
            f"{st['peak']['label']}的{y_name}最高（{_fmt(st['peak']['value'])}），"
            f"{st['trough']['label']}最低（{_fmt(st['trough']['value'])}）"
        )
        if conc:
            facts.append(
                {
                    "type": "concentration",
                    "title": "集中度",
                    "text": (
                        f"头部 1 项占 {conc['top1_share']*100:.0f}%，前 3 项合计占 {conc['top3_share']*100:.0f}%，"
                        f"末尾的 {conc['bottom_label']} 仅占 {conc['bottom_share']*100:.0f}%。"
                    ),
                }
            )
            if conc["top3_share"] > 0.7:
                summary_parts.append("结构高度集中，前 3 项贡献超过 70%")

        chart_hint = {
            "type": "bar",
            "x": columns[c_idx],
            "y": y_name,
            "labels": labels,
            "values": values,
            "mark_peak": st["peak"]["index"],
            "mark_trough": st["trough"]["index"],
        }

    summary = "；".join(summary_parts) + "。" if summary_parts else f"共返回 {len(rows)} 行，{y_name} 合计 {_fmt(sum(v for _, v in points))}。"

    return {"summary": summary, "facts": facts, "chart_hint": chart_hint, "points": []}


def hypotheses(columns: list[str], rows: list[list], insights: dict, question: str | None = None) -> list[str]:
    """基于数据模式给出**待核实**的影响因素，不编造外部事实。"""
    hints: list[str] = []
    kinds = classify(columns, rows)

    # 若识别出了用户关心的对比对象，先给一条针对性的推测
    for f in insights.get("facts", []):
        if f.get("type") == "compare":
            hints.append(
                "两个日期的差距可能来自活动排期、发薪日或库存节奏；"
                "建议核对这两天是否有促销、缺货或系统异常，再用更长周期验证是否为固定规律"
            )
            break

    if not kinds["date"] or not kinds["numeric"]:
        return hints or ["以上为基于数据模式的推测，需结合业务实际情况确认"]

    y_idx = kinds["numeric"][0]
    d_idx = kinds["date"][0]
    series = []
    for r in rows:
        d = _parse_date(r[d_idx])
        if d and _is_number(r[y_idx]):
            series.append((d, float(r[y_idx])))
    series.sort(key=lambda x: x[0])
    if len(series) < 10:
        return hints

    types = {f["type"] for f in insights.get("facts", [])}
    if "weekday" in types:
        hints.append("存在明显周内波动，建议核实是否为休息日/工作日作息导致的客流差异")
    if "day_of_month" in types:
        hints.append("月初与月末差异明显，可能与发薪日、促销活动周期或账单结算日有关")
    if "drop" in types:
        hints.append("出现过单期大幅下滑，建议核对当日是否有断货、系统故障或投放暂停")
    if not hints:
        hints.append("数据呈平稳波动，未发现明显的星期或月初规律")
    hints.append("以上为基于数据模式的推测，需结合业务实际情况确认")
    return hints

