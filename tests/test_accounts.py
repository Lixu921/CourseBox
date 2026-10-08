import sqlite3

import pytest
from conftest import create_client, login_admin, login_user


def test_authentication_and_role_permissions(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    assert client.post(
        "/接口/登录", json={"username": "admin", "password": "wrong-pass"}
    ).status_code == 401
    assert client.post("/接口/课程", json={"name": "Anonymous Blocked"}).status_code == 401

    admin = login_user(client, "admin", "admin12345")
    assert admin["username"] == "admin"
    assert admin["role"] == "admin"
    assert client.get("/接口/当前用户").json() == admin

    assert client.post(
        "/接口/用户",
        json={"username": "uploader1", "password": "uploader-pass", "role": "uploader"},
    ).status_code == 201
    assert client.post(
        "/接口/用户",
        json={"username": "viewer1", "password": "viewer-pass", "role": "viewer"},
    ).status_code == 201

    course = client.post("/接口/课程", json={"name": "Permission Course"}).json()
    viewer = create_client()
    login_user(viewer, "viewer1", "viewer-pass")
    assert viewer.post("/接口/课程", json={"name": "Viewer Blocked"}).status_code == 403
    assert viewer.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "blocked"},
        files={"file": ("blocked.txt", b"blocked", "text/plain")},
    ).status_code == 403

    uploader = create_client()
    login_user(uploader, "uploader1", "uploader-pass")
    uploaded = uploader.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "Pending Notes"},
        files={"file": ("pending.txt", b"pending-content", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["status"] == "pending"

    assert client.post(
        "/接口/用户",
        json={"username": "uploader1", "password": "uploader-pass", "role": "uploader"},
    ).status_code == 409
    assert uploader.get("/接口/当前用户").json()["role"] == "uploader"
    assert uploader.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 1


def test_production_requires_explicit_admin_password(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("COURSEBOX_ENV", "production")
    monkeypatch.delenv("COURSEBOX_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="COURSEBOX_ADMIN_PASSWORD"):
        get_settings()

    monkeypatch.setenv("COURSEBOX_ADMIN_PASSWORD", "short")
    with pytest.raises(RuntimeError, match="至少"):
        get_settings()

    monkeypatch.setenv("COURSEBOX_ADMIN_PASSWORD", "a-long-enough-password")
    settings = get_settings()
    assert settings.is_production is True
    assert settings.cookie_secure is True


def test_development_falls_back_to_default_password(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("COURSEBOX_ENV", "development")
    monkeypatch.delenv("COURSEBOX_ADMIN_PASSWORD", raising=False)
    settings = get_settings()

    assert settings.admin_password == "admin12345"
    assert settings.is_production is False
    # 局域网通常是 http，开发环境默认不加 Secure，否则浏览器不回传 Cookie。
    assert settings.cookie_secure is False


def test_login_cookie_respects_secure_setting(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_COOKIE_SECURE", "true")

    from app.db import init_db

    init_db()
    response = client.post(
        "/接口/登录", json={"username": "admin", "password": "admin12345"}
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie


def test_login_lockout_after_repeated_failures(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("COURSEBOX_LOGIN_LOCKOUT_SECONDS", "60")

    from app.db import init_db

    init_db()
    wrong = {"username": "admin", "password": "wrong-pass"}
    assert client.post("/接口/登录", json=wrong).status_code == 401
    assert client.post("/接口/登录", json=wrong).status_code == 401

    locked = client.post("/接口/登录", json=wrong)
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_requests"

    # 锁定期间即使密码正确也要被挡下。
    blocked = client.post(
        "/接口/登录", json={"username": "admin", "password": "admin12345"}
    )
    assert blocked.status_code == 429


def test_login_success_clears_failure_counter(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("COURSEBOX_LOGIN_LOCKOUT_SECONDS", "60")

    from app.db import init_db

    init_db()
    wrong = {"username": "admin", "password": "wrong-pass"}
    assert client.post("/接口/登录", json=wrong).status_code == 401
    assert client.post("/接口/登录", json=wrong).status_code == 401

    assert login_user(client, "admin", "admin12345")["role"] == "admin"

    # 计数已清零，重新失败两次仍然只是 401 而不是锁定。
    assert client.post("/接口/登录", json=wrong).status_code == 401
    assert client.post("/接口/登录", json=wrong).status_code == 401
    assert client.post("/接口/登录", json=wrong).status_code == 429


def test_admin_user_management(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    admin = login_user(client, "admin", "admin12345")

    assert client.post(
        "/接口/用户",
        json={"username": "helper", "password": "helper-pass", "role": "uploader"},
    ).status_code == 201

    listing = client.get("/接口/用户")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert [item["username"] for item in body["items"]] == ["admin", "helper"]
    helper = body["items"][1]
    assert helper["role"] == "uploader"
    assert helper["is_active"] is True
    assert helper["upload_count"] == 0
    assert helper["created_at"]

    # 关键词与角色筛选。
    filtered = client.get("/接口/用户", params={"关键词": "help"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["username"] == "helper"
    assert client.get("/接口/用户", params={"角色": "admin"}).json()["total"] == 1
    assert client.get("/接口/用户", params={"角色": "viewer"}).json()["total"] == 0

    # 改角色。
    promoted = client.patch(
        f"/接口/用户/{helper['id']}", json={"role": "viewer"}
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "viewer"

    # 空请求体没有可改的字段。
    assert client.patch(f"/接口/用户/{helper['id']}", json={}).status_code == 422
    assert client.patch("/接口/用户/99999", json={"role": "viewer"}).status_code == 404

    # 不能改自己的角色，也不能停用自己。
    assert client.patch(
        f"/接口/用户/{admin['id']}", json={"role": "viewer"}
    ).status_code == 409
    assert client.patch(
        f"/接口/用户/{admin['id']}", json={"is_active": False}
    ).status_code == 409
    assert client.get("/接口/当前用户").json()["role"] == "admin"


def test_last_active_admin_is_protected(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_user(client, "admin", "admin12345")
    second = client.post(
        "/接口/用户",
        json={"username": "admin2", "password": "admin2-pass", "role": "admin"},
    ).json()

    # 有两个启用的管理员时可以停用其中一个。
    assert client.patch(
        f"/接口/用户/{second['id']}", json={"is_active": False}
    ).status_code == 200
    assert client.get("/接口/用户", params={"启用": True}).json()["total"] == 1

    # 只剩一个启用管理员后，降权与停用都要被拒绝。
    assert client.patch(
        f"/接口/用户/{second['id']}", json={"role": "viewer"}
    ).status_code == 200
    assert client.get("/接口/用户", params={"角色": "admin"}).json()["total"] == 1
    assert client.get("/接口/用户", params={"启用": False}).json()["total"] == 1

    second_admin = client.post(
        "/接口/用户",
        json={"username": "admin3", "password": "admin3-pass", "role": "admin"},
    ).json()
    assert client.patch(
        f"/接口/用户/{second_admin['id']}", json={"is_active": False}
    ).status_code == 200
    assert client.patch(
        f"/接口/用户/{second_admin['id']}", json={"role": "viewer"}
    ).status_code == 200


def test_disabled_user_cannot_login_and_sessions_are_revoked(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    created = client.post(
        "/接口/用户",
        json={"username": "temp", "password": "temp-pass", "role": "uploader"},
    ).json()

    worker = create_client()
    login_user(worker, "temp", "temp-pass")
    assert worker.get("/接口/当前用户").status_code == 200

    assert client.patch(
        f"/接口/用户/{created['id']}", json={"is_active": False}
    ).json()["is_active"] is False

    # 已登录会话立即失效。
    assert worker.get("/接口/当前用户").status_code == 401
    # 重新登录被拒绝，且提示是停用而不是密码错误。
    retry = worker.post(
        "/接口/登录", json={"username": "temp", "password": "temp-pass"}
    )
    assert retry.status_code == 403
    assert "停用" in retry.json()["error"]["message"]

    # 重新启用后可以登录。
    assert client.patch(
        f"/接口/用户/{created['id']}", json={"is_active": True}
    ).json()["is_active"] is True
    assert worker.post(
        "/接口/登录", json={"username": "temp", "password": "temp-pass"}
    ).status_code == 200


def test_admin_resets_user_password(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    created = client.post(
        "/接口/用户",
        json={"username": "resetme", "password": "old-password", "role": "viewer"},
    ).json()

    worker = create_client()
    login_user(worker, "resetme", "old-password")

    assert client.post(
        f"/接口/用户/{created['id']}/重置密码", json={"password": "short"}
    ).status_code == 422
    assert client.post(
        f"/接口/用户/{created['id']}/重置密码", json={"password": "new-password"}
    ).status_code == 204
    assert client.post(
        "/接口/用户/99999/重置密码", json={"password": "new-password"}
    ).status_code == 404

    # 旧会话作废，旧密码失效，新密码可用。
    assert worker.get("/接口/当前用户").status_code == 401
    assert worker.post(
        "/接口/登录", json={"username": "resetme", "password": "old-password"}
    ).status_code == 401
    assert worker.post(
        "/接口/登录", json={"username": "resetme", "password": "new-password"}
    ).status_code == 200


def test_user_changes_own_password(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    client.post(
        "/接口/用户",
        json={"username": "selfserve", "password": "old-password", "role": "uploader"},
    )

    mine = create_client()
    login_user(mine, "selfserve", "old-password")
    assert mine.get("/接口/当前用户").json()["username"] == "selfserve"

    assert mine.post(
        "/接口/我的密码",
        json={"current_password": "old-password", "new_password": "brand-new-pass"},
    ).status_code == 204

    # 旧密码失效、新密码可用。
    assert mine.post(
        "/接口/登录", json={"username": "selfserve", "password": "old-password"}
    ).status_code == 401
    assert mine.post(
        "/接口/登录", json={"username": "selfserve", "password": "brand-new-pass"}
    ).status_code == 200

    # 审计里能看出是本人改的，而不是管理员重置的。
    records = client.get("/接口/审计", params={"动作": "reset_password"}).json()["items"]
    assert any("用户自助修改密码" in (item["detail"] or "") for item in records), records


def test_change_password_keeps_current_session_drops_others(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    client.post(
        "/接口/用户",
        json={"username": "twodevices", "password": "old-password", "role": "viewer"},
    )

    laptop = create_client()
    phone = create_client()
    login_user(laptop, "twodevices", "old-password")
    login_user(phone, "twodevices", "old-password")
    assert phone.get("/接口/当前用户").status_code == 200

    assert laptop.post(
        "/接口/我的密码",
        json={"current_password": "old-password", "new_password": "another-pass"},
    ).status_code == 204

    # 改密码的那台设备不该被自己踢下线……
    assert laptop.get("/接口/当前用户").status_code == 200
    # ……其它设备上的会话必须失效。
    assert phone.get("/接口/当前用户").status_code == 401


def test_change_password_rejects_wrong_or_invalid_input(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)

    anonymous = create_client()
    assert anonymous.post(
        "/接口/我的密码",
        json={"current_password": "admin12345", "new_password": "whatever-pass"},
    ).status_code == 401

    # 当前密码不对。
    assert client.post(
        "/接口/我的密码",
        json={"current_password": "not-the-password", "new_password": "whatever-pass"},
    ).status_code == 400
    # 新密码太短、与当前密码相同、字段缺失，都由 schema 拦下。
    assert client.post(
        "/接口/我的密码",
        json={"current_password": "admin12345", "new_password": "short"},
    ).status_code == 422
    assert client.post(
        "/接口/我的密码",
        json={"current_password": "admin12345", "new_password": "admin12345"},
    ).status_code == 422
    assert client.post("/接口/我的密码", json={"new_password": "whatever-pass"}).status_code == 422
    # 密码没被改坏，原密码仍然能登录。
    assert create_client().post(
        "/接口/登录", json={"username": "admin", "password": "admin12345"}
    ).status_code == 200


def test_non_admin_cannot_manage_users(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    created = client.post(
        "/接口/用户",
        json={"username": "plain", "password": "plain-pass", "role": "uploader"},
    ).json()

    worker = create_client()
    login_user(worker, "plain", "plain-pass")

    assert worker.get("/接口/用户").status_code == 403
    assert worker.patch(
        f"/接口/用户/{created['id']}", json={"role": "admin"}
    ).status_code == 403
    assert worker.post(
        f"/接口/用户/{created['id']}/重置密码", json={"password": "another-pass"}
    ).status_code == 403
    assert worker.post(
        "/接口/用户",
        json={"username": "sneaky", "password": "sneaky-pass", "role": "admin"},
    ).status_code == 403
    assert client.get("/接口/用户", params={"关键词": "sneaky"}).json()["total"] == 0


def _age_session(tmp_path, *, days: int) -> sqlite3.Connection:
    """把当前会话的有效期改到「只剩 days 天」，用来触发滑动续期。"""

    from app.db import configure_connection

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "UPDATE sessions SET expires_at = datetime('now', ?)", (f"+{days} days",)
    )
    connection.commit()
    return connection


def test_active_session_is_renewed(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)

    # 剩余 1 天 < 一半阈值（3.5 天），下一次请求应该把有效期推回满值。
    connection = _age_session(tmp_path, days=1)
    before = connection.execute("SELECT expires_at FROM sessions").fetchone()[0]

    response = client.get("/接口/当前用户")
    assert response.status_code == 200
    # 顺延必须同时重发 Cookie，否则浏览器会按旧期限先把 Cookie 丢掉。
    assert "set-cookie" in response.headers

    after = connection.execute("SELECT expires_at FROM sessions").fetchone()[0]
    assert after > before
    remaining = connection.execute(
        "SELECT julianday(expires_at) - julianday('now') FROM sessions"
    ).fetchone()[0]
    assert remaining > 6
    connection.close()


def test_fresh_session_is_not_renewed(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import configure_connection, init_db

    init_db()
    login_admin(client)

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    before = connection.execute("SELECT expires_at FROM sessions").fetchone()[0]

    response = client.get("/接口/当前用户")
    assert response.status_code == 200
    # 刚登录还有整整 7 天，不该每个请求都去改写数据库。
    assert "set-cookie" not in response.headers
    after = connection.execute("SELECT expires_at FROM sessions").fetchone()[0]
    assert after == before
    connection.close()


def test_session_renewal_reaches_file_downloads(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "续期"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "资料"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    ).json()

    connection = _age_session(tmp_path, days=1)

    # 下载接口直接返回 FileResponse，FastAPI 不会合并依赖里设的响应头，
    # 所以续期只能靠最外层中间件补 Set-Cookie。这条用例专门守住这条链路。
    response = client.get(f"/接口/资料/{uploaded['id']}/下载")
    assert response.status_code == 200
    assert "set-cookie" in response.headers

    remaining = connection.execute(
        "SELECT julianday(expires_at) - julianday('now') FROM sessions"
    ).fetchone()[0]
    assert remaining > 6
    connection.close()


def test_logout_clears_session_without_renewing(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)

    # 会话已到该续期的时候，退出登录也不能顺手把它续上。
    connection = _age_session(tmp_path, days=1)

    response = client.post("/接口/退出")
    assert response.status_code == 204
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1
    assert "Max-Age=0" in cookies[0]
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    connection.close()


def test_session_expires_at_absolute_lifetime_cap(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import configure_connection, init_db

    init_db()
    login_admin(client)

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    # 会话是 31 天前建立的，已越过 30 天绝对上限：再怎么活跃也得重新登录。
    connection.execute("UPDATE sessions SET created_at = datetime('now', '-31 days')")
    connection.commit()

    assert client.get("/接口/当前用户").status_code == 401
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    connection.close()


def test_renewal_never_passes_absolute_lifetime_cap(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import configure_connection, init_db

    init_db()
    login_admin(client)

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    # 会话 29 天前建立：还能续，但最多只能续到第 30 天。
    connection.execute(
        "UPDATE sessions SET created_at = datetime('now', '-29 days'), "
        "expires_at = datetime('now', '+1 day')"
    )
    connection.commit()

    assert client.get("/接口/当前用户").status_code == 200
    remaining = connection.execute(
        "SELECT julianday(expires_at) - julianday('now') FROM sessions"
    ).fetchone()[0]
    # 剩余不到 2 天，而不是被续成满 7 天——说明绝对上限确实压住了续期。
    assert 0 < remaining < 2
    connection.close()


def test_invalid_cookie_does_not_write_to_database(tmp_path, monkeypatch):
    """无效 Cookie 不该在读路径上写库。

    以前 find_session_user 查不到会话时会顺手删一遍过期的 sessions——而无效 Cookie
    是外部随便就能构造的，等于把一个写操作暴露给了任何请求。现在过期会话改由启动
    维护和 `py -m app.maintenance` 清理。
    """

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import configure_connection, init_db

    init_db()

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('ghost', 'x', 'viewer')"
    )
    user_id = connection.execute(
        "SELECT id FROM users WHERE username = 'ghost'"
    ).fetchone()[0]
    # 一条已经过期的会话，充当「有没有偷偷写库」的哨兵。
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at)"
        " VALUES (?, 'expired-token-hash', datetime('now', '-1 day'))",
        (user_id,),
    )
    connection.commit()

    client = create_client()
    # 把无效 Cookie 设在客户端上（逐请求传 cookies= 已被 httpx 标记为弃用）。
    client.cookies.set("coursebox_session", "not-a-real-token")
    response = client.get("/接口/当前用户")
    assert response.status_code == 401

    # 过期会话仍在原处：这次请求没有顺手删库。
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    connection.close()


def test_purge_expired_sessions_removes_only_expired(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import configure_connection, init_db, purge_expired_sessions

    init_db()

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('u', 'x', 'viewer')"
    )
    user_id = connection.execute("SELECT id FROM users WHERE username = 'u'").fetchone()[0]
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at)"
        " VALUES (?, 'stale', datetime('now', '-1 day'))",
        (user_id,),
    )
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at)"
        " VALUES (?, 'live', datetime('now', '+1 day'))",
        (user_id,),
    )
    connection.commit()

    assert purge_expired_sessions(connection) == 1
    remaining = [row[0] for row in connection.execute("SELECT token_hash FROM sessions")]
    assert remaining == ["live"]
    connection.close()
