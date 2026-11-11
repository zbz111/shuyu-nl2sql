"""导入真实公开数据集：UCI Online Retail（英国在线零售商 2010-12 ~ 2011-12 交易明细）。

数据来源：https://archive.ics.uci.edu/dataset/352/online+retail
- 541,909 行原始交易，真实业务数据；
- 清洗规则：剔除退货单（InvoiceNo 以 C 开头）、数量/单价 <= 0 的记录；
- 派生字段：revenue = quantity * unit_price，invoice_date、weekday、hour。

用法：.venv\\Scripts\\python.exe scripts/import_online_retail.py
输出：data/real/online_retail.db
"""
from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

import httpx
import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "real"
CACHE = OUT_DIR / "online_retail.zip"
DB = OUT_DIR / "online_retail.db"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def download() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and CACHE.stat().st_size > 20_000_000:
        print(f"使用缓存 {CACHE}（{CACHE.stat().st_size/1024/1024:.1f} MB）")
        return CACHE
    print(f"下载 {URL} ...")
    with httpx.Client(timeout=180, follow_redirects=True) as c:
        r = c.get(URL)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    print(f"已下载 {CACHE.stat().st_size/1024/1024:.1f} MB")
    return CACHE


def load_frame(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
        print(f"解压读取 {name} ...")
        with z.open(name) as fh:
            df = pd.read_excel(io.BytesIO(fh.read()), dtype={"InvoiceNo": str, "StockCode": str})
    print(f"原始行数：{len(df):,}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["InvoiceNo", "StockCode", "InvoiceDate", "Quantity", "UnitPrice"])
    before = len(df)
    df = df[~df["InvoiceNo"].astype(str).str.upper().str.startswith("C")]
    cancelled = before - len(df)
    df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]
    df = df.copy()
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    df["Revenue"] = (df["Quantity"] * df["UnitPrice"]).round(2)
    dt = pd.to_datetime(df["InvoiceDate"])
    df["InvoiceDate"] = dt
    df["date"] = dt.dt.strftime("%Y-%m-%d")
    df["month"] = dt.dt.strftime("%Y-%m")
    df["weekday"] = dt.dt.weekday.map(lambda i: WEEKDAY_CN[i])
    df["hour"] = dt.dt.hour
    df["Country"] = df["Country"].astype(str)
    df["CustomerID"] = df["CustomerID"].astype("Int64")
    print(f"剔除退货单 {cancelled:,} 行；剔除异常数量/单价后剩 {len(df):,} 行")
    return df


def build_db(df: pd.DataFrame, db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE orders (
            row_id      INTEGER PRIMARY KEY,
            invoice_no  TEXT NOT NULL,
            stock_code  TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity    INTEGER NOT NULL,
            unit_price  REAL NOT NULL,
            revenue     REAL NOT NULL,
            invoice_date TEXT NOT NULL,
            month       TEXT NOT NULL,
            weekday     TEXT NOT NULL,
            hour        INTEGER NOT NULL,
            customer_id INTEGER,
            country     TEXT NOT NULL
        );
        """
    )
    rows = [
        (
            i,
            str(r.InvoiceNo),
            str(r.StockCode),
            r.Description,
            int(r.Quantity),
            float(r.UnitPrice),
            float(r.Revenue),
            r.date,
            r.month,
            r.weekday,
            int(r.Hour) if hasattr(r, "Hour") else int(r.hour),
            int(r.CustomerID) if pd.notna(r.CustomerID) else None,
            r.Country,
        )
        for i, r in enumerate(df.itertuples(index=False))
    ]
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    cur.executescript(
        """
        CREATE TABLE products AS
        SELECT stock_code,
               MAX(description) AS description,
               COUNT(*)        AS order_lines,
               ROUND(SUM(quantity), 2) AS total_qty,
               ROUND(SUM(revenue), 2)  AS total_revenue
        FROM orders GROUP BY stock_code;

        CREATE TABLE customers AS
        SELECT customer_id,
               MAX(country) AS country,
               COUNT(DISTINCT invoice_no) AS order_count,
               ROUND(SUM(revenue), 2)     AS total_revenue
        FROM orders WHERE customer_id IS NOT NULL GROUP BY customer_id;

        CREATE TABLE countries AS
        SELECT country,
               COUNT(*)                AS order_lines,
               COUNT(DISTINCT invoice_no) AS order_count,
               ROUND(SUM(revenue), 2)  AS total_revenue
        FROM orders GROUP BY country;

        CREATE INDEX idx_orders_date ON orders(invoice_date);
        CREATE INDEX idx_orders_month ON orders(month);
        CREATE INDEX idx_orders_customer ON orders(customer_id);
        """
    )
    conn.commit()

    for table in ("orders", "products", "customers", "countries"):
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n:,} 行")
    span = cur.execute("SELECT MIN(invoice_date), MAX(invoice_date) FROM orders").fetchone()
    total = cur.execute("SELECT ROUND(SUM(revenue), 2) FROM orders").fetchone()[0]
    print(f"  日期范围：{span[0]} ~ {span[1]}")
    print(f"  总销售额：{total:,.2f}")
    conn.close()
    print(f"数据库：{db_path}  ({db_path.stat().st_size/1024/1024:.1f} MB)")


def main() -> None:
    df = clean(load_frame(download()))
    build_db(df, DB)


if __name__ == "__main__":
    main()