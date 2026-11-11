"""生成两份 CSV 演示数据，用来测试"上传 → 分析 → 出图"链路。

用法：.venv\\Scripts\\python.exe scripts\\make_demo_csv.py
输出：data/demo_csv/
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "demo_csv"
OUT.mkdir(parents=True, exist_ok=True)


def daily_sales() -> Path:
    """90 天日销售额：月初冲高、月中回落、周末偏低，模拟真实零售节奏。"""
    random.seed(2026)
    rows = []
    d = date(2026, 7, 1)
    for _ in range(92):
        base = 12000.0
        dom = d.day
        if dom <= 3:
            base *= 1.55          # 月初冲高（发薪 + 平台活动）
        elif 4 <= dom <= 8:
            base *= 0.72          # 月初预算用完后回落
        elif 25 <= dom:
            base *= 1.15          # 月末清仓
        if d.weekday() >= 5:
            base *= 0.83          # 周末线下客流下降
        if d.month == 8 and 10 <= d.day <= 16:
            base *= 1.25          # 8 月大促
        amount = round(base * random.uniform(0.92, 1.08), 2)
        orders = max(1, int(amount / random.uniform(180, 260)))
        rows.append([d.isoformat(), amount, orders, round(amount / orders, 2)])
        d += timedelta(days=1)

    path = OUT / "日销售数据.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["日期", "销售额", "订单数", "客单价"])
        w.writerows(rows)
    return path


def product_sales() -> Path:
    rows = [
        ["智能音箱 X1", "数码", 1820, 544180],
        ["智能音箱 X1 Pro", "数码", 960, 479040],
        ["无线耳机 Air", "数码", 1450, 578550],
        ["机械键盘 K8", "数码", 620, 222580],
        ["显示器 27 寸", "数码", 210, 272790],
        ["保温杯 500ml", "生活", 2310, 205590],
        ["护眼台灯", "生活", 1180, 152220],
        ["跑步鞋", "运动", 890, 408510],
        ["瑜伽垫", "运动", 1620, 127980],
        ["健身哑铃 10kg", "运动", 540, 107460],
    ]
    path = OUT / "商品销售明细.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["商品", "品类", "销量", "销售额"])
        w.writerows(rows)
    return path


if __name__ == "__main__":
    for p in (daily_sales(), product_sales()):
        print(f"生成 {p}  ({p.stat().st_size / 1024:.1f} KB)")