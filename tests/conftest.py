"""pytest 配置：独立测试库 + 固定 SQL 的假模型，保证测试离线可跑。"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / ".testtmp"
if TMP.exists():
    shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True, exist_ok=True)
(TMP / "uploads").mkdir(parents=True, exist_ok=True)

DEMO_DB = TMP / "demo.db"


def _build_demo_db() -> None:
    conn = sqlite3.connect(DEMO_DB)
    conn.executescript(
        """
        CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, qty INTEGER, order_date TEXT);
        INSERT INTO products VALUES (1,'音箱','数码',299),(2,'台灯','生活',129),(3,'跑鞋','运动',459);
        INSERT INTO orders VALUES (1,1,2,'2026-01-05'),(2,1,1,'2026-02-11'),(3,2,5,'2026-02-20'),
                                  (4,3,1,'2026-03-02'),(5,3,2,'2026-03-15');
        """
    )
    conn.commit()
    conn.close()


_build_demo_db()

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(TMP / 'app.db').as_posix()}",
        "DATA_DIR": str(TMP),
        "UPLOAD_DIR": str(TMP / "uploads"),
        "LLM_PROVIDER": "hash",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin123",
        "SECRET_KEY": "test-secret-key-for-pytest-only-0123456789",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.services import generator, narration  # noqa: E402

FAKE_SQL = (
    "SELECT p.category AS 品类, ROUND(SUM(o.qty * p.price), 2) AS 销售额 "
    "FROM orders o JOIN products p ON p.id = o.product_id GROUP BY p.category ORDER BY 销售额 DESC"
)


@pytest.fixture(scope="session", autouse=True)
def fake_llm():
    """不依赖真实模型：生成固定 SQL，结论固定文案。"""
    original_generate = generator.generate
    original_fix = generator.fix
    original_summarize = narration.summarize

    generator.generate = lambda q, ddl, history=None, notes="", *a, **k: (FAKE_SQL, 10)  # type: ignore[assignment]
    generator.fix = lambda q, ddl, bad, err, notes="", *a, **k: FAKE_SQL  # type: ignore[assignment]
    narration.summarize = lambda q, cols, rows: "数码品类销售额最高。"  # type: ignore[assignment]
    yield
    generator.generate = original_generate
    generator.fix = original_fix
    narration.summarize = original_summarize


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def datasource_id(client, auth):
    with DEMO_DB.open("rb") as fh:
        r = client.post(
            "/api/v1/datasources/upload",
            files={"file": ("demo.db", fh, "application/octet-stream")},
            headers=auth,
        )
    assert r.status_code == 201, r.text
    return r.json()["id"]
