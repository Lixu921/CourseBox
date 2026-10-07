from conftest import _upload_named, create_client, login_admin, login_user


def _make_user(client, username: str, role: str = "uploader") -> dict:
    response = client.post(
        "/接口/用户",
        json={"username": username, "password": f"{username}-pass", "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _user_map(client) -> dict:
    page = client.get("/接口/用户", params={"page_size": 100}).json()
    return {item["id"]: item for item in page["items"]}


def test_batch_update_users_enables_and_disables(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    first = _make_user(client, "batch-one")
    second = _make_user(client, "batch-two")

    disabled = client.post(
        "/接口/用户/批量修改",
        json={"ids": [first["id"], second["id"]], "action": "disable"},
    )
    assert disabled.status_code == 200
    assert (disabled.json()["succeeded"], disabled.json()["failed"]) == (2, 0)

    users = _user_map(client)
    assert users[first["id"]]["is_active"] is False
    assert users[second["id"]]["is_active"] is False

    enabled = client.post(
        "/接口/用户/批量修改",
        json={"ids": [first["id"]], "action": "enable"},
    )
    assert enabled.json()["succeeded"] == 1
    users = _user_map(client)
    assert users[first["id"]]["is_active"] is True
    assert users[second["id"]]["is_active"] is False


def test_batch_update_users_reports_each_failure(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    target = _make_user(client, "batch-partial")
    me = client.get("/接口/当前用户").json()

    # 一个正常、一个不存在、一个是我自己（不能停用自己）。
    response = client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"], 999999, me["id"]], "action": "disable"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (1, 2)

    results = {item["id"]: item for item in body["items"]}
    assert results[target["id"]]["ok"] is True
    assert results[999999]["ok"] is False
    assert results[999999]["message"] == "用户不存在"
    # 批量接口复用单条逻辑，所以「不能停用自己」这条规则照样拦得住。
    assert results[me["id"]]["ok"] is False
    assert results[me["id"]]["message"] == "不能停用当前登录的账户"
    assert _user_map(client)[me["id"]]["is_active"] is True


def test_batch_update_users_changes_role(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    target = _make_user(client, "batch-role")

    response = client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"]], "action": "role", "role": "viewer"},
    )
    assert response.json()["succeeded"] == 1
    assert _user_map(client)[target["id"]]["role"] == "viewer"

    # 改角色却不给目标角色属于请求错误，不能静默成功。
    assert client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"]], "action": "role"},
    ).status_code == 422
    # 空编号列表同理。
    assert client.post(
        "/接口/用户/批量修改",
        json={"ids": [], "action": "enable"},
    ).status_code == 422


def test_batch_review_files_approves_and_rejects(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "批量审核"}).json()
    # 管理员上传默认是已通过，这里靠批量审核把它改成别的状态。
    first = _upload_named(client, course["id"], "甲", "a.txt", b"a")
    second = _upload_named(client, course["id"], "乙", "b.txt", b"b")
    third = _upload_named(client, course["id"], "丙", "c.txt", b"c")

    rejected = client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"]], "status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["succeeded"] == 2

    files = client.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    statuses = {item["id"]: item["status"] for item in files}
    assert statuses[first["id"]] == "rejected"
    assert statuses[second["id"]] == "rejected"
    assert statuses[third["id"]] == "approved"

    approved = client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"], 999999], "status": "approved"},
    )
    body = approved.json()
    assert (body["succeeded"], body["failed"]) == (2, 1)
    results = {item["id"]: item for item in body["items"]}
    assert results[first["id"]]["message"] == "已通过"
    assert results[999999]["message"] == "资料不存在"

    files = client.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    assert {item["id"]: item["status"] for item in files}[first["id"]] == "approved"


def test_batch_review_records_one_audit_entry_per_file(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "批量审核审计"}).json()
    first = _upload_named(client, course["id"], "甲", "a.txt", b"a")
    second = _upload_named(client, course["id"], "乙", "b.txt", b"b")

    assert client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"]], "status": "rejected"},
    ).status_code == 200

    records = client.get("/接口/审计", params={"动作": "rejected"}).json()
    assert records["total"] >= 2
    # 批量操作也是逐条记审计，而不是只记一条「批量审核」。
    assert {item["entity_id"] for item in records["items"]} >= {first["id"], second["id"]}


def test_batch_endpoints_require_admin(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    _make_user(client, "batch-plain", role="viewer")

    anonymous = create_client()
    assert anonymous.post(
        "/接口/用户/批量修改", json={"ids": [1], "action": "disable"}
    ).status_code == 401
    assert anonymous.post(
        "/接口/资料/批量审核", json={"ids": [1], "status": "approved"}
    ).status_code == 401

    viewer = create_client()
    login_user(viewer, "batch-plain", "batch-plain-pass")
    assert viewer.post(
        "/接口/用户/批量修改", json={"ids": [1], "action": "disable"}
    ).status_code == 403
    assert viewer.post(
        "/接口/资料/批量审核", json={"ids": [1], "status": "approved"}
    ).status_code == 403
