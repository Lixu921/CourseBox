from conftest import create_client, login_admin, login_user


def _setup(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "评论课"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "可评论资料"},
        files={"file": ("a.txt", b"a", "text/plain")},
    ).json()
    return client, course, uploaded


def test_comment_read_and_post(tmp_path, monkeypatch):
    client, course, uploaded = _setup(tmp_path, monkeypatch)
    anonymous = create_client()

    # 匿名能读，但不能发。
    listing = anonymous.get(f"/接口/资料/{uploaded['id']}/评论").json()
    assert listing["total"] == 0
    assert (
        anonymous.post(
            f"/接口/资料/{uploaded['id']}/评论", json={"body": "hi"}
        ).status_code
        == 401
    )

    posted = client.post(
        f"/接口/资料/{uploaded['id']}/评论", json={"body": "  第一条  "}
    )
    assert posted.status_code == 201
    body = posted.json()
    # 首尾空白被去掉；带上作者用户名。
    assert body["body"] == "第一条"
    assert body["username"] == "admin"

    listing = anonymous.get(f"/接口/资料/{uploaded['id']}/评论").json()
    assert listing["total"] == 1
    assert listing["items"][0]["body"] == "第一条"

    # 评论数出现在课程资料列表里。
    files = anonymous.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    assert files[0]["comment_count"] == 1


def test_comment_validation(tmp_path, monkeypatch):
    client, _course, uploaded = _setup(tmp_path, monkeypatch)

    assert client.post(
        f"/接口/资料/{uploaded['id']}/评论", json={"body": "   "}
    ).status_code == 422
    assert client.post(
        f"/接口/资料/{uploaded['id']}/评论", json={"body": "x" * 2001}
    ).status_code == 422
    assert client.post(f"/接口/资料/{uploaded['id']}/评论", json={}).status_code == 422


def test_comment_delete_permissions(tmp_path, monkeypatch):
    client, _course, uploaded = _setup(tmp_path, monkeypatch)
    admin_comment = client.post(
        f"/接口/资料/{uploaded['id']}/评论", json={"body": "管理员评论"}
    ).json()

    client.post(
        "/接口/用户",
        json={"username": "commenter", "password": "commenter-pass", "role": "uploader"},
    )
    other = create_client()
    login_user(other, "commenter", "commenter-pass")

    # 别人不能删我的评论。
    assert other.delete(f"/接口/评论/{admin_comment['id']}").status_code == 403

    # 管理员能删别人的评论。
    other_comment = other.post(
        f"/接口/资料/{uploaded['id']}/评论", json={"body": "路人评论"}
    ).json()
    assert client.delete(f"/接口/评论/{other_comment['id']}").status_code == 204

    # 作者能删自己的评论。
    own = other.post(f"/接口/资料/{uploaded['id']}/评论", json={"body": "再发一条"}).json()
    assert other.delete(f"/接口/评论/{own['id']}").status_code == 204

    assert client.delete("/接口/评论/999999").status_code == 404


def test_pending_file_comments_are_hidden(tmp_path, monkeypatch):
    client, course, _uploaded = _setup(tmp_path, monkeypatch)
    client.post(
        "/接口/用户",
        json={"username": "pendinguser", "password": "pending-pass", "role": "uploader"},
    )
    uploader = create_client()
    login_user(uploader, "pendinguser", "pending-pass")
    pending = uploader.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审资料"},
        files={"file": ("p.txt", b"p", "text/plain")},
    ).json()

    # 待审资料的评论对陌生人和匿名都不可见；本人与管理员可见。
    resource = f"/接口/资料/{pending['id']}/评论"
    assert create_client().get(resource).status_code == 404
    assert uploader.get(resource).status_code == 200
    assert client.get(resource).status_code == 200
