from conftest import create_client


def _client(tmp_path, monkeypatch, **env):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    from app.db import init_db

    init_db()
    return client


def test_register_and_auto_login(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/接口/注册", json={"username": "newbie", "password": "newbie-pass"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "newbie"
    assert body["role"] == "uploader"
    # 注册成功即已登录。
    assert client.get("/接口/当前用户").json()["username"] == "newbie"


def test_register_one_account_per_ip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert (
        client.post(
            "/接口/注册", json={"username": "first", "password": "first-pass"}
        ).status_code
        == 201
    )

    # 同一来源 IP 再注册被拒。
    second = create_client()
    blocked = second.post(
        "/接口/注册", json={"username": "second", "password": "second-pass"}
    )
    assert blocked.status_code == 409
    assert "已经注册" in blocked.json()["error"]["message"]


def test_register_validation_and_username_uniqueness(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, COURSEBOX_TRUST_PROXY="true")

    assert (
        client.post(
            "/接口/注册", json={"username": "ab", "password": "ab-passwd"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/接口/注册", json={"username": "abc", "password": "short"}
        ).status_code
        == 422
    )

    # 用不同 X-Forwarded-For 模拟不同来源 IP：用户名唯一约束独立生效。
    assert (
        client.post(
            "/接口/注册",
            json={"username": "dupe", "password": "dupe-pass"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        ).status_code
        == 201
    )
    clash = create_client().post(
        "/接口/注册",
        json={"username": "dupe", "password": "dupe-pass"},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert clash.status_code == 409
    assert "用户名已存在" in clash.json()["error"]["message"]


def test_register_can_be_disabled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, COURSEBOX_ALLOW_REGISTRATION="false")
    response = client.post(
        "/接口/注册", json={"username": "nobody", "password": "nobody-pass"}
    )
    assert response.status_code == 403


def test_register_never_grants_admin(tmp_path, monkeypatch):
    # 即使把注册角色配成 admin，也只会回退到默认 uploader。
    client = _client(tmp_path, monkeypatch, COURSEBOX_REGISTER_ROLE="admin")
    body = client.post(
        "/接口/注册", json={"username": "selfadmin", "password": "self-pass"}
    ).json()
    assert body["role"] == "uploader"
