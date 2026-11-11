"""生成演示数据库 data/sales.db（零售销售数据），用于开箱体验。

用法：python scripts/seed_demo.py
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "sales.db"

PRODUCTS = [
    ("智能音箱 X1", "数码", 299.0, 120.0),
    ("智能音箱 X1 Pro", "数码", 499.0, 210.0),
    ("无线耳机 Air", "数码", 399.0, 150.0),
    ("机械键盘 K8", "数码", 359.0, 160.0),
    ("显示器 27 寸", "数码", 1299.0, 900.0),
    ("保温杯 500ml", "生活", 89.0, 30.0),
    ("护眼台灯", "生活", 129.0, 55.0),
    ("跑步鞋", "运动", 459.0, 210.0),
    ("瑜伽垫", "运动", 79.0, 25.0),
    ("健身哑铃 10kg", "运动", 199.0, 80.0),
]

CITIES = ["大连", "沈阳", "北京", "上海", "深圳", "杭州", "成都", "青岛"]
LEVELS = ["普通", "银卡", "金卡", "黑卡"]
CHANNELS = ["APP", "小程序", "门店", "天猫", "京东"]


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            cost REAL NOT NULL
        );
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            city TEXT NOT NULL,
            level TEXT NOT NULL,
            register_date TEXT NOT NULL
        );
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            order_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL
        );
        """
    )

    for i, (name, cat, price, cost) in enumerate(PRODUCTS, start=1):
        cur.execute("INSERT INTO products VALUES (?,?,?,?,?)", (i, name, cat, price, cost))

    random.seed(2026)
    surnames = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈"]
    for cid in range(1, 81):
        name = random.choice(surnames) + random.choice(["先生", "女士"])
        city = random.choice(CITIES)
        level = random.choices(LEVELS, weights=[55, 25, 15, 5])[0]
        reg = (date(2025, 1, 1) + timedelta(days=random.randint(0, 600))).isoformat()
        cur.execute("INSERT INTO customers VALUES (?,?,?,?,?)", (cid, name, city, level, reg))

    start = date(2026, 1, 1)
    rows = []
    for oid in range(1, 2401):
        pid = random.randint(1, len(PRODUCTS))
        base_price = PRODUCTS[pid - 1][2]
        qty = random.choices([1, 1, 1, 2, 2, 3], k=1)[0]
        discount = random.choice([1.0, 1.0, 1.0, 0.95, 0.9])
        order_date = start + timedelta(days=random.randint(0, 299))
        status = random.choices(["已完成", "已完成", "已完成", "已取消", "退货"], weights=[70, 10, 10, 6, 4])[0]
        rows.append(
            (
                oid,
                pid,
                random.randint(1, 80),
                qty,
                round(base_price * discount, 2),
                order_date.isoformat(),
                random.choice(CHANNELS),
                status,
            )
        )
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    for table in ("products", "customers", "orders"):
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count} 行")
    conn.close()
    print(f"已生成 {DB}")


if __name__ == "__main__":
    main()
