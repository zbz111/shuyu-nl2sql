"""端到端冒烟：登录 → 上传 sales.db → 表结构 → 自然语言查询 → 手动 SQL → 历史。

用法：.venv\\Scripts\\python.exe scripts\\e2e_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"
DB = Path("data/sales.db")


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=180) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        r.raise_for_status()
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("[1] 登录成功")

        existing = c.get("/api/v1/datasources", headers=headers).json()
        ds = next((d for d in existing if d["kind"] == "sqlite"), None)
        if ds is None:
            with DB.open("rb") as fh:
                r = c.post("/api/v1/datasources/upload", headers=headers, files={"file": ("sales.db", fh)})
            r.raise_for_status()
            ds = r.json()
        print(f"[2] 数据源 id={ds['id']} name={ds['name']} tables={ds['table_count']}")

        tables = c.get(f"/api/v1/datasources/{ds['id']}/tables", headers=headers).json()
        for t in tables:
            print(f"    {t['name']}: {len(t['columns'])} 列, {t['row_count']} 行")

        print("[3] 自然语言查询")
        r = c.post(
            "/api/v1/query",
            headers=headers,
            json={"datasource_id": ds["id"], "question": "每个品类的销售额是多少？按销售额从高到低"},
        )
        r.raise_for_status()
        data = r.json()
        print("    SQL:", " ".join(data["sql"].split())[:160])
        print("    状态:", data["status"], "| 行数:", data["row_count"], "| 耗时:", data["latency_ms"], "ms")
        print("    列:", data["columns"])
        print("    首行:", data["rows"][0] if data["rows"] else None)
        print("    结论:", data["narration"])
        print("    图表:", data["chart"])

        print("[4] 手动 SQL")
        r = c.post(
            "/api/v1/query/execute",
            headers=headers,
            json={"datasource_id": ds["id"], "sql": "SELECT city, COUNT(*) AS 客户数 FROM customers GROUP BY city"},
        )
        body = r.json()
        print("    状态:", body["status"], "行数:", body["row_count"])
        print("    首行:", body["rows"][0] if body["rows"] else None)

        print("[5] 危险 SQL 拦截")
        r = c.post(
            "/api/v1/query/execute",
            headers=headers,
            json={"datasource_id": ds["id"], "sql": "DELETE FROM orders"},
        )
        print("    状态:", r.json()["status"], "|", r.json()["error"])

        print("[6] 历史")
        hist = c.get("/api/v1/queries", headers=headers, params={"limit": 5}).json()
        print(f"    {len(hist)} 条，最新：{hist[0]['question'] if hist else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
