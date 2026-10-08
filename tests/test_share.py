import sqlite3

from conftest import create_client, login_admin, login_user


def _prepare(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "分享课程"}).json()
    client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "已通过资料"},
        files={"file": ("ok.txt", b"ok", "text/plain")},
    )
    return client, course


def test_share_link_lifecycle(tmp_path, monkeypatch):
    client, course = _prepare(tmp_path, monkeypatch)

    # 上传者的待审资料不应出现在分享页。
    client.post(
        "/接口/用户",
        json={"username": "pending", "password": "pending-pass", "role": "uploader"},
    )
    uploader = create_client()
    login_user(uploader, "pending", "pending-pass")
    uploader.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审资料"},
        files={"file": ("p.txt", b"p", "text/plain")},
    )

    created = client.post(
        f"/接口/课程/{course['id']}/分享", json={"days": 7, "note": "给同学"}
    )
    assert created.status_code == 201
    body = created.json()
    token = body["token"]
    assert body["url"] == f"/分享/{token}"
    assert body["note"] == "给同学"

    anonymous = create_client()
    view = anonymous.get(f"/接口/分享/{token}")
    assert view.status_code == 200
    data = view.json()
    assert data["course"]["name"] == "分享课程"
    assert data["note"] == "给同学"
    assert [item["title"] for item in data["files"]] == ["已通过资料"]
    # 分享页 HTML 不需要登录也能打开。
    assert anonymous.get(f"/分享/{token}").status_code == 200

    # 非管理员不能创建。
    client.post(
        "/接口/用户",
        json={"username": "viewer", "password": "viewer-pass", "role": "viewer"},
    )
    viewer = create_client()
    login_user(viewer, "viewer", "viewer-pass")
    assert viewer.post(f"/接口/课程/{course['id']}/分享", json={}).status_code == 403

    # 撤销后链接失效。
    shares = client.get(f"/接口/课程/{course['id']}/分享").json()
    assert len(shares) == 1
    assert client.delete(f"/接口/分享/{shares[0]['id']}").status_code == 204
    assert anonymous.get(f"/接口/分享/{token}").status_code == 404


def test_expired_share_link_is_gone(tmp_path, monkeypatch):
    client, course = _prepare(tmp_path, monkeypatch)
    token = client.post(
        f"/接口/课程/{course['id']}/分享", json={"days": 1}
    ).json()["token"]

    connection = sqlite3.connect(tmp_path / "test.db")
    connection.execute("UPDATE share_links SET expires_at = datetime('now', '-1 day')")
    connection.commit()
    connection.close()

    response = create_client().get(f"/接口/分享/{token}")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "gone"
