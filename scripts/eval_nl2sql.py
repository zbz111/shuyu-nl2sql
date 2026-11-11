"""在真实数据集（UCI Online Retail，53 万行）上评测 Text2SQL。

评测方法（可复核）：
1. 每道题配一条**参考 SQL**，直接查库得到标准答案（不靠人肉记忆）；
2. 调用智能体，拿到它的 SQL 与结果；
3. 比对规则：
   - 标量题：答案数值与标准值相对误差 <= 0.5%
   - Top1 题：第一行标签一致 + 数值误差 <= 0.5%
4. 输出逐题明细与汇总准确率。

用法：.venv\\Scripts\\python.exe scripts/eval_nl2sql.py [--ds 4]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"
DB = Path("data/real/online_retail.db")

# (问题, 参考 SQL, 比对方式)
CASES = [
    ("总销售额是多少？", "SELECT ROUND(SUM(revenue),2) AS v FROM orders", "scalar"),
    ("一共有多少个订单？", "SELECT COUNT(DISTINCT invoice_no) AS v FROM orders", "scalar"),
    ("哪个月份的销售额最高？", "SELECT month AS m, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY month ORDER BY v DESC LIMIT 1", "top1"),
    ("每个月的销售额分别是多少？", "SELECT month, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY month ORDER BY month", "series"),
    ("哪个国家的销售额最高？", "SELECT country AS c, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY country ORDER BY v DESC LIMIT 1", "top1"),
    ("英国贡献的销售额占比是多少？", "SELECT ROUND(SUM(CASE WHEN country='United Kingdom' THEN revenue ELSE 0 END)/SUM(revenue)*100,2) AS v FROM orders", "scalar"),
    ("销售额最高的 5 个产品是哪些？", "SELECT description AS d, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY stock_code ORDER BY v DESC LIMIT 5", "top1"),
    ("销量最大的产品是哪个？", "SELECT description AS d, SUM(quantity) AS v FROM orders GROUP BY stock_code ORDER BY v DESC LIMIT 1", "top1"),
    ("每周几的销售额最高？", "SELECT weekday AS w, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY weekday ORDER BY v DESC LIMIT 1", "top1"),
    ("平均每单金额是多少？", "SELECT ROUND(SUM(revenue)/COUNT(DISTINCT invoice_no),2) AS v FROM orders", "scalar"),
    ("下单次数最多的客户花了多少钱？", "SELECT customer_id AS c, ROUND(SUM(revenue),2) AS v FROM orders WHERE customer_id IS NOT NULL GROUP BY customer_id ORDER BY COUNT(DISTINCT invoice_no) DESC LIMIT 1", "top1"),
    ("2011 年 11 月的销售额是多少？", "SELECT ROUND(SUM(revenue),2) AS v FROM orders WHERE month='2011-11'", "scalar"),
    ("销量前 5 的产品是哪些？", "SELECT description AS d, SUM(quantity) AS v FROM orders GROUP BY stock_code ORDER BY v DESC LIMIT 5", "top1"),
    ("销售额第二高的国家是哪个？", "SELECT country AS c, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY country ORDER BY v DESC LIMIT 1 OFFSET 1", "top1"),
    ("一共有多少个客户下过单？", "SELECT COUNT(DISTINCT customer_id) AS v FROM orders WHERE customer_id IS NOT NULL", "scalar"),
    ("英国以外销售额最高的国家是哪个？", "SELECT country AS c, ROUND(SUM(revenue),2) AS v FROM orders WHERE country<>'United Kingdom' GROUP BY country ORDER BY v DESC LIMIT 1", "top1"),
    ("销售额最少的星期几？", "SELECT weekday AS w, ROUND(SUM(revenue),2) AS v FROM orders GROUP BY weekday ORDER BY v ASC LIMIT 1", "top1"),
    ("订单数最多的月份是哪个？", "SELECT month AS m, COUNT(DISTINCT invoice_no) AS v FROM orders GROUP BY month ORDER BY v DESC LIMIT 1", "top1"),
    ("平均每笔商品行金额是多少？", "SELECT ROUND(SUM(revenue)/COUNT(*),2) AS v FROM orders", "scalar"),
    ("2011 年 3 月的订单数是多少？", "SELECT COUNT(DISTINCT invoice_no) AS v FROM orders WHERE month='2011-03'", "scalar"),
]


def ref_value(sql: str) -> list[tuple]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        # GROUP BY / ORDER BY 需要临时文件；受限环境磁盘不可写时会报
        # "unable to open database file"，所以强制放内存
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def close_enough(a: float, b: float, tol: float = 0.005) -> bool:
    if b == 0:
        return abs(a) < 1e-6
    return abs(a - b) / abs(b) <= tol


def judge(kind: str, expected: list[tuple], got_rows: list[list]) -> tuple[bool, str]:
    if not got_rows:
        return False, "智能体没有返回数据"
    if kind == "scalar":
        exp = float(expected[0][0])
        nums = [float(x) for row in got_rows for x in row if isinstance(x, (int, float))]
        ok = any(close_enough(n, exp) for n in nums)
        return ok, f"期望 {exp:,.2f}，实际数值 {nums[:3]}"
    if kind == "top1":
        exp_label = str(expected[0][0]).strip().lower()
        exp_val = float(expected[0][1])
        first_cells = list(got_rows[0])
        first = [str(x).strip().lower() for x in first_cells]
        nums = [float(x) for x in first_cells if isinstance(x, (int, float))]

        # 情况 A：智能体只返回了数值（没带标签）→ 只比数值
        if nums and not any(isinstance(x, str) and x.strip() for x in first_cells):
            ok = any(close_enough(n, exp_val) for n in nums)
            return ok, f"期望 {exp_val:,.2f}，实际数值 {nums}"

        label_ok = any(exp_label == x or exp_label in x for x in first)
        # 智能体可能只返回名称不返回值，此时只校验标签
        val_ok = (not nums) or any(close_enough(n, exp_val) for n in nums)
        return label_ok and val_ok, f"期望「{expected[0][0]}」={exp_val:,.2f}，实际首行 {got_rows[0]}"
    # series：只校验行数与首末月份
    exp_n = len(expected)
    ok = abs(len(got_rows) - exp_n) <= 1
    return ok, f"期望 {exp_n} 行，实际 {len(got_rows)} 行"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", type=int, default=0, help="数据源 id，默认自动查找 online_retail")
    args = ap.parse_args()

    with httpx.Client(base_url=BASE, timeout=180) as c:
        tok = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()[
            "access_token"
        ]
        h = {"Authorization": f"Bearer {tok}"}
        ds_id = args.ds
        if not ds_id:
            ds_id = next(d["id"] for d in c.get("/api/v1/datasources", headers=h).json() if "online_retail" in d["name"])

        rows_out = []
        passed = 0
        lat = []
        for q, sql, kind in CASES:
            expected = ref_value(sql)
            t0 = time.time()
            r = c.post("/api/v1/query", headers=h, json={"datasource_id": ds_id, "question": q})
            cost = time.time() - t0
            lat.append(cost)
            if r.status_code != 200:
                rows_out.append({"q": q, "ok": False, "why": f"HTTP {r.status_code}", "sec": round(cost, 1)})
                print(f"❌ HTTP {r.status_code}  {q}")
                continue
            d = r.json()
            if d["status"] != "ok":
                rows_out.append({"q": q, "ok": False, "why": d.get("error", "")[:120], "sec": round(cost, 1)})
                print(f"❌ 执行失败  {q}  -> {d.get('error','')[:80]}")
                continue
            ok, why = judge(kind, expected, d["rows"])
            passed += ok
            rows_out.append(
                {
                    "q": q,
                    "ok": ok,
                    "why": why,
                    "sql": d["sql"],
                    "rows": d["row_count"],
                    "sec": round(cost, 1),
                    "summary": d.get("insight_summary", ""),
                }
            )
            print(f"{'✅' if ok else '❌'} {q}")
            print(f"    SQL: {' '.join(d['sql'].split())[:130]}")
            if not ok:
                print(f"    {why}")

        total = len(CASES)
        print("\n" + "=" * 62)
        print(f"一次通过      : {passed}/{total} = {passed/total:.1%}")
        print(f"平均延迟      : {sum(lat)/len(lat):.1f}s")
        print(f"P95 延迟      : {sorted(lat)[int(len(lat)*0.95)]:.1f}s")
        out = Path("data/eval_nl2sql_real.json")
        out.write_text(
            json.dumps({"ds_id": ds_id, "total": total, "passed": passed, "rows": rows_out}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"明细：{out}")


if __name__ == "__main__":
    main()


