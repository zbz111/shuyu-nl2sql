"""接口测试：认证、数据源、查询、安全拦截、历史。"""
from __future__ import annotations


def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_login_wrong(client):
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401


def test_datasource_upload_and_tables(client, auth, datasource_id):
    r = client.get("/api/v1/datasources", headers=auth)
    assert r.status_code == 200
    assert any(d["id"] == datasource_id for d in r.json())

    r = client.get(f"/api/v1/datasources/{datasource_id}/tables", headers=auth)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    assert {"products", "orders"} <= names


def test_nl_query_ok(client, auth, datasource_id):
    r = client.post(
        "/api/v1/query",
        json={"datasource_id": datasource_id, "question": "每个品类的销售额是多少"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok", data
    assert data["columns"] == ["品类", "销售额"]
    assert data["row_count"] == 3
    assert data["narration"]


def test_manual_sql_blocked(client, auth, datasource_id):
    r = client.post(
        "/api/v1/query/execute",
        json={"datasource_id": datasource_id, "sql": "DROP TABLE orders"},
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_manual_sql_ok(client, auth, datasource_id):
    r = client.post(
        "/api/v1/query/execute",
        json={"datasource_id": datasource_id, "sql": "SELECT COUNT(*) AS n FROM orders"},
        headers=auth,
    )
    body = r.json()
    assert body["status"] == "ok", body
    assert body["rows"][0][0] == 5


def test_history_and_favorite(client, auth, datasource_id):
    r = client.get(f"/api/v1/queries?datasource_id={datasource_id}", headers=auth)
    assert r.status_code == 200 and r.json()
    qid = r.json()[0]["id"]
    r = client.post(f"/api/v1/queries/{qid}/favorite", headers=auth)
    assert r.json()["favorite"] is True
    r = client.get(f"/api/v1/queries?datasource_id={datasource_id}&favorite=true", headers=auth)
    assert any(x["id"] == qid for x in r.json())


def test_permission_isolation(client, auth, datasource_id):
    client.post(
        "/api/v1/admin/users",
        json={"username": "u2", "password": "user123", "display_name": "普通用户"},
        headers=auth,
    )
    token = client.post("/api/v1/auth/login", json={"username": "u2", "password": "user123"}).json()["access_token"]
    r = client.get(f"/api/v1/datasources/{datasource_id}/tables", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
