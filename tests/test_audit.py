from conftest import create_client, login_admin, login_user


def test_resource_governance_and_audit_logs(tmp_path, monkeypatch):
    import sqlite3

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_dir))

    from app.db import init_db

    init_db()
    login_admin(client)
    assert client.post(
        "/接口/用户",
        json={"username": "uploader1", "password": "uploader-pass", "role": "uploader"},
    ).status_code == 201
    assert client.post(
        "/接口/用户",
        json={"username": "uploader2", "password": "uploader-pass", "role": "uploader"},
    ).status_code == 201
    course = client.post("/接口/课程", json={"name": "Governed Course"}).json()

    uploader1 = create_client()
    login_user(uploader1, "uploader1", "uploader-pass")
    pending = uploader1.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "Pending Material"},
        files={"file": ("pending.txt", b"pending", "text/plain")},
    ).json()
    pending_id = pending["id"]

    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 1
    assert create_client().get(
        f"/接口/课程/{course['id']}/资料"
    ).json()["total"] == 0
    assert create_client().get(
        "/接口/搜索", params={"q": "Pending Material"}
    ).json()["total"] == 0
    assert create_client().get(f"/接口/资料/{pending_id}/下载").status_code == 404
    assert uploader1.get(f"/接口/资料/{pending_id}/下载").content == b"pending"

    uploader2 = create_client()
    login_user(uploader2, "uploader2", "uploader-pass")
    other = uploader2.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "Other Material"},
        files={"file": ("other.txt", b"other", "text/plain")},
    ).json()
    assert uploader1.patch(
        f"/接口/资料/{other['id']}", json={"title": "Not Allowed"}
    ).status_code == 403
    assert uploader1.delete(f"/接口/资料/{other['id']}").status_code == 403

    rejected = client.patch(
        f"/接口/资料/{pending_id}/审核", json={"status": "rejected"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert create_client().get(f"/接口/资料/{pending_id}/下载").status_code == 404
    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 2

    approved = client.patch(
        f"/接口/资料/{other['id']}/审核", json={"status": "approved"}
    )
    assert approved.status_code == 200
    public_client = create_client()
    public_files = public_client.get(f"/接口/课程/{course['id']}/资料").json()
    assert public_files["total"] == 1
    assert public_files["items"][0]["id"] == other["id"]
    assert public_client.get(f"/接口/资料/{other['id']}/下载").content == b"other"
    assert public_client.get("/接口/搜索", params={"q": "Other Material"}).json()["total"] == 1

    connection = sqlite3.connect(tmp_path / "test.db")
    actions = {
        row[0]
        for row in connection.execute("SELECT action FROM audit_logs").fetchall()
    }
    assert {"login", "create", "upload", "rejected", "approved", "download"} <= actions
    connection.close()


def test_audit_logs_are_purged_by_retention(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db, purge_audit_logs

    init_db()
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.executescript(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, created_at)
        VALUES (NULL, 'old', 'file', datetime('now', '-100 days'));
        INSERT INTO audit_logs (actor_id, action, entity_type, created_at)
        VALUES (NULL, 'new', 'file', datetime('now'));
        """
    )
    connection.commit()

    assert purge_audit_logs(connection, 90) == 1
    remaining = [row[0] for row in connection.execute("SELECT action FROM audit_logs")]
    assert remaining == ["new"]

    # 保留期设为 0 表示全部保留。
    assert purge_audit_logs(connection, 0) == 0
    assert connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 1
    connection.close()


def test_audit_log_listing_for_admins(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()

    # 未登录不能看操作记录。
    assert client.get("/接口/审计").status_code == 401

    login_admin(client)
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "绪论"},
        files={"file": ("intro.pdf", b"a" * 32, "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text

    page = client.get("/接口/审计").json()
    assert page["total"] >= 3
    assert page["page"] == 1
    # 最新的记录排在最前面。
    ids = [item["id"] for item in page["items"]]
    assert ids == sorted(ids, reverse=True)
    # 操作人用户名由 LEFT JOIN 带出来，而不是只给一个 id。
    assert page["items"][0]["actor_name"] == "admin"
    assert {"login", "create"} <= {item["action"] for item in page["items"]}

    only_login = client.get("/接口/审计", params={"动作": "login"}).json()
    assert only_login["total"] >= 1
    assert {item["action"] for item in only_login["items"]} == {"login"}

    only_course = client.get("/接口/审计", params={"对象": "course"}).json()
    assert only_course["total"] >= 1
    assert {item["entity_type"] for item in only_course["items"]} == {"course"}

    matched = client.get("/接口/审计", params={"关键词": "数据结构"}).json()
    assert matched["total"] >= 1

    # 参数校验与分页。
    assert client.get("/接口/审计", params={"动作": "bogus"}).status_code == 422
    assert (
        client.get(
            "/接口/审计", params={"起始时间": "2026-01-02", "结束时间": "2026-01-01"}
        ).status_code
        == 422
    )
    paged = client.get("/接口/审计", params={"page": 1, "page_size": 2}).json()
    assert len(paged["items"]) == 2
    assert paged["total_pages"] == (paged["total"] + 1) // 2

    # 非管理员不能看。
    created = client.post(
        "/接口/用户",
        json={"username": "viewer1", "password": "viewer12345", "role": "viewer"},
    )
    assert created.status_code == 201, created.text
    viewer = create_client()
    login_user(viewer, "viewer1", "viewer12345")
    assert viewer.get("/接口/审计").status_code == 403


def test_anonymous_download_is_not_audited(tmp_path, monkeypatch):
    """公开下载不写审计：否则任何人都能用匿名下载把 audit_logs 刷爆。"""

    import sqlite3

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "Public Course"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "Public Doc"},
        files={"file": ("public.txt", b"hi", "text/plain")},
    ).json()
    file_id = uploaded["id"]

    connection = sqlite3.connect(tmp_path / "test.db")
    connection.execute("DELETE FROM audit_logs")
    connection.commit()

    anonymous = create_client()
    assert anonymous.get(f"/接口/资料/{file_id}/下载").status_code == 200
    assert anonymous.get(f"/接口/资料/{file_id}/下载").status_code == 200
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'download'"
        ).fetchone()[0]
        == 0
    )

    # 登录用户下载仍然留痕。
    assert client.get(f"/接口/资料/{file_id}/下载").status_code == 200
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'download'"
        ).fetchone()[0]
        == 1
    )
    connection.close()


def test_audit_cursor_pagination(tmp_path, monkeypatch):
    """审计用游标分页：按 offset 翻页会在持续写入时跳条/重复。"""

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    for index in range(4):
        client.post("/接口/课程", json={"name": f"课程{index}"})

    first = client.get("/接口/审计", params={"page_size": 2}).json()
    first_ids = [item["id"] for item in first["items"]]
    assert len(first_ids) == 2
    cursor = first_ids[-1]

    second = client.get(
        "/接口/审计", params={"page_size": 2, "游标": cursor}
    ).json()
    second_ids = [item["id"] for item in second["items"]]
    assert second_ids
    # 第二页全部严格小于游标，且与第一页没有交集。
    assert all(item_id < cursor for item_id in second_ids)
    assert set(first_ids).isdisjoint(second_ids)

    # 游标必须是正整数。
    assert client.get("/接口/审计", params={"游标": 0}).status_code == 422
