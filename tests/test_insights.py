from conftest import create_client, login_admin, login_user


def _setup(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "洞察课"}).json()
    first = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "甲"},
        files={"file": ("a.txt", b"a", "text/plain")},
    ).json()
    second = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "乙"},
        files={"file": ("b.txt", b"b", "text/plain")},
    ).json()
    return client, course, first, second


def test_download_count_and_hot_recent(tmp_path, monkeypatch):
    client, course, first, second = _setup(tmp_path, monkeypatch)
    anonymous = create_client()

    for _ in range(3):
        assert anonymous.get(f"/接口/资料/{first['id']}/下载").status_code == 200
    assert anonymous.get(f"/接口/资料/{second['id']}/下载").status_code == 200

    hot = anonymous.get("/接口/热门").json()["items"]
    assert [item["title"] for item in hot][:2] == ["甲", "乙"]
    assert hot[0]["download_count"] == 3
    assert hot[0]["course"]["name"] == "洞察课"

    # 最新按编号倒序：乙后传，排前面。
    recent = anonymous.get("/接口/最新").json()["items"]
    assert [item["title"] for item in recent][:2] == ["乙", "甲"]

    # 课程资料列表也带下载次数。
    files = anonymous.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    assert {item["title"]: item["download_count"] for item in files} == {"甲": 3, "乙": 1}


def test_overview_is_admin_only(tmp_path, monkeypatch):
    client, course, _first, _second = _setup(tmp_path, monkeypatch)

    assert create_client().get("/接口/概览").status_code == 401

    client.post(
        "/接口/用户",
        json={"username": "user1", "password": "u1-password", "role": "uploader"},
    )
    uploader = create_client()
    login_user(uploader, "user1", "u1-password")
    uploader.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审"},
        files={"file": ("p.txt", b"p", "text/plain")},
    )

    overview = client.get("/接口/概览").json()
    assert overview["courses"] == 1
    assert overview["files"] == {
        "approved": 2,
        "pending": 1,
        "rejected": 0,
        "total": 3,
    }
    assert overview["users_total"] == 2
    assert overview["users_active"] == 2
    assert overview["storage_bytes"] == 3
    assert overview["trash"] == 0
    assert overview["downloads"] == 0


def test_my_sessions_list_and_revoke(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)

    phone = create_client()
    login_user(phone, "admin", "admin12345")

    listing = client.get("/接口/我的会话").json()["items"]
    assert len(listing) == 2
    assert sum(1 for item in listing if item["current"]) == 1
    # 不暴露令牌，但要能看出设备信息。
    assert all("token" not in item for item in listing)
    assert all(item["user_agent"] for item in listing)

    target = next(item for item in listing if not item["current"])
    assert client.delete(f"/接口/我的会话/{target['id']}").status_code == 204
    # 被撤销的设备立即失效。
    assert phone.get("/接口/当前用户").status_code == 401
    assert len(client.get("/接口/我的会话").json()["items"]) == 1

    assert client.delete("/接口/我的会话/999999").status_code == 404
