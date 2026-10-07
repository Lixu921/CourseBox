from conftest import _upload_named, create_client, login_admin, login_user


def test_course_archive_packs_selected_files(tmp_path, monkeypatch):
    import io
    import zipfile

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "打包课程"}).json()
    first = _upload_named(client, course["id"], "第一份", "first.txt", b"first-content")
    second = _upload_named(client, course["id"], "第二份", "second.txt", b"second-content")
    _upload_named(client, course["id"], "第三份", "third.txt", b"third-content")

    # 只勾选前两份，第三份不应出现在包里。
    response = client.get(
        f"/接口/课程/{course['id']}/打包下载",
        params=[("资料编号", first["id"]), ("资料编号", second["id"])],
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert sorted(bundle.namelist()) == ["first.txt", "second.txt"]
        assert bundle.read("first.txt") == b"first-content"
        assert bundle.read("second.txt") == b"second-content"

    # 不传编号表示整门课。
    everything = client.get(f"/接口/课程/{course['id']}/打包下载")
    assert everything.status_code == 200
    with zipfile.ZipFile(io.BytesIO(everything.content)) as bundle:
        assert sorted(bundle.namelist()) == ["first.txt", "second.txt", "third.txt"]

    # 重复传同一个编号不会把同一份文件塞两遍。
    repeated = client.get(
        f"/接口/课程/{course['id']}/打包下载",
        params=[("资料编号", first["id"]), ("资料编号", first["id"])],
    )
    with zipfile.ZipFile(io.BytesIO(repeated.content)) as bundle:
        assert bundle.namelist() == ["first.txt"]


def test_course_archive_renames_duplicate_entries(tmp_path, monkeypatch):
    import io
    import zipfile

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "重名课程"}).json()
    # 内容不同、文件名相同，才绕得过去重索引。
    _upload_named(client, course["id"], "同名甲", "同名.txt", b"aaa")
    _upload_named(client, course["id"], "同名乙", "同名.txt", b"bbb")
    _upload_named(client, course["id"], "同名丙", "同名.txt", b"ccc")

    response = client.get(f"/接口/课程/{course['id']}/打包下载")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        names = sorted(bundle.namelist())
        assert names == ["同名(1).txt", "同名(2).txt", "同名.txt"]
        # 内容不能串位：每一份都还是自己那一份。
        assert {bundle.read(name) for name in names} == {b"aaa", b"bbb", b"ccc"}


def test_course_archive_respects_visibility(tmp_path, monkeypatch):
    import io
    import zipfile

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "可见性课程"}).json()
    assert client.post(
        "/接口/用户",
        json={"username": "packer", "password": "packer-pass", "role": "uploader"},
    ).status_code == 201

    worker = create_client()
    login_user(worker, "packer", "packer-pass")
    pending = _upload_named(worker, course["id"], "待审核", "pending.txt", b"pending")
    assert client.patch(
        f"/接口/资料/{pending['id']}/审核", json={"status": "approved"}
    ).status_code == 200
    # 再传一份仍是待审核状态的。
    still_pending = _upload_named(
        worker, course["id"], "仍是待审核", "still-pending.txt", b"pending2"
    )

    visitor = create_client()
    response = visitor.get(f"/接口/课程/{course['id']}/打包下载")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert bundle.namelist() == ["pending.txt"]

    # 上传者本人能看到自己的待审核资料，所以整包有两份。
    mine = worker.get(f"/接口/课程/{course['id']}/打包下载")
    with zipfile.ZipFile(io.BytesIO(mine.content)) as bundle:
        assert sorted(bundle.namelist()) == ["pending.txt", "still-pending.txt"]

    # 访客点名要待审核那两份也拿不到，只会拿到自己可见的已通过资料。
    denied = visitor.get(
        f"/接口/课程/{course['id']}/打包下载",
        params=[
            ("资料编号", pending["id"]),
            ("资料编号", still_pending["id"]),
        ],
    )
    with zipfile.ZipFile(io.BytesIO(denied.content)) as bundle:
        assert bundle.namelist() == ["pending.txt"]


def test_course_archive_rejects_missing_targets(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)

    assert client.get("/接口/课程/999/打包下载").status_code == 404

    empty = client.post("/接口/课程", json={"name": "空课程"}).json()
    assert client.get(f"/接口/课程/{empty['id']}/打包下载").status_code == 404

    course = client.post("/接口/课程", json={"name": "有资料课程"}).json()
    uploaded = _upload_named(client, course["id"], "唯一一份", "only.txt", b"only")
    # 点名一个不存在的编号：没有任何命中，应报 404 而不是给一个空压缩包。
    missing = client.get(
        f"/接口/课程/{course['id']}/打包下载", params=[("资料编号", 99999)]
    )
    assert missing.status_code == 404

    # 已进回收站的资料不能被打包。
    assert client.delete(f"/接口/资料/{uploaded['id']}").status_code == 204
    assert client.get(f"/接口/课程/{course['id']}/打包下载").status_code == 404


def test_course_archive_is_audited(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "审计打包课程"}).json()
    _upload_named(client, course["id"], "打包审计", "audit-pack.txt", b"audit-pack")

    assert client.get(f"/接口/课程/{course['id']}/打包下载").status_code == 200
    records = client.get("/接口/审计", params={"动作": "download"}).json()
    assert records["total"] >= 1
    top = records["items"][0]
    assert top["entity_type"] == "course"
    assert top["entity_id"] == course["id"]
    assert "打包下载 1 份资料" in top["detail"]
