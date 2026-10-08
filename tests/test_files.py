from urllib.parse import unquote

from conftest import create_client, login_admin, login_user
from fastapi.testclient import TestClient

from app.main import app


def quota_client(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    return client


def test_file_title_and_filename_have_length_limits(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "课程"}).json()
    too_long_title = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "x" * 201},
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    too_long_name = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "资料"},
        files={"file": ("x" * 256 + ".txt", b"notes", "text/plain")},
    )
    assert too_long_title.status_code == 422
    assert too_long_name.status_code == 422
    assert not list((tmp_path / "uploads").glob("*"))


def test_empty_title_does_not_leave_upload_open_or_file(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/api/courses", json={"name": "course"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "   "},
        files={"file": ("lesson.txt", b"content", "text/plain")},
    )

    assert response.status_code == 422
    assert not list((tmp_path / "uploads").glob("*"))


def test_upload_and_list_files(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/\u63a5\u53e3/\u8bfe\u7a0b", json={"name": "Data Structures"}).json()
    response = client.post(
        f"/\u63a5\u53e3/\u8bfe\u7a0b/{course['id']}/\u8d44\u6599",
        data={"title": "Lesson"},
        files={"file": ("lesson.txt", b"hello CourseBox", "text/plain")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["original_name"] == "lesson.txt"
    assert uploaded["size"] == len(b"hello CourseBox")

    files_response = client.get(
        f"/\u63a5\u53e3/\u8bfe\u7a0b/{course['id']}/\u8d44\u6599"
    )

    assert files_response.status_code == 200
    assert files_response.json()["items"][0]["title"] == "Lesson"


def test_upload_to_missing_course_returns_404():
    client = create_client()
    login_admin(client)
    response = client.post(
        "/\u63a5\u53e3/\u8bfe\u7a0b/999999/\u8d44\u6599",
        data={"title": "Lesson"},
        files={"file": ("lesson.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


def test_download_and_search_file(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/\u63a5\u53e3/\u8bfe\u7a0b", json={"name": "Data Structures"}).json()
    upload = client.post(
        f"/\u63a5\u53e3/\u8bfe\u7a0b/{course['id']}/\u8d44\u6599",
        data={"title": "Tree Notes"},
        files={"file": ("data-structures.pdf", b"pdf-content", "application/pdf")},
    )
    file_id = upload.json()["id"]

    download = client.get(f"/\u63a5\u53e3/\u8d44\u6599/{file_id}/\u4e0b\u8f7d")
    search = client.get("/\u63a5\u53e3/\u641c\u7d22", params={"q": "Data Structures"})

    assert download.status_code == 200
    assert download.content == b"pdf-content"
    assert "data-structures.pdf" in unquote(download.headers["content-disposition"])
    assert search.status_code == 200
    assert search.json()["items"][0]["course"]["name"] == "Data Structures"


def test_search_empty_query_returns_empty_list(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    response = client.get("/\u63a5\u53e3/\u641c\u7d22", params={"q": "   "})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_upload_rejects_unsupported_and_empty_files(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/api/courses", json={"name": "course"}).json()

    executable = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "unsafe"},
        files={"file": ("run.exe", b"not executable", "application/octet-stream")},
    )
    disguised = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "disguised"},
        files={"file": ("notes.txt", b"not executable", "application/x-dosexec")},
    )
    empty = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "empty"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert executable.status_code == 415
    assert disguised.status_code == 415
    assert empty.status_code == 422
    assert not list((tmp_path / "uploads").glob("*"))


def test_upload_rejects_executable_extension_even_when_configured(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSEBOX_ALLOWED_EXTENSIONS", ".txt,.exe")

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "课程"}).json()
    response = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "危险文件"},
        files={"file": ("run.exe", b"not executable", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert not list((tmp_path / "uploads").glob("*"))


def test_download_rejects_path_outside_upload_directory(tmp_path, monkeypatch):
    import sqlite3

    client = create_client()
    database = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    outside = tmp_path / "outside.txt"
    monkeypatch.setenv("COURSEBOX_DB", str(database))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_dir))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "课程"}).json()
    connection = sqlite3.connect(database)
    connection.execute(
        "INSERT INTO files (course_id, title, filename, original_name, size) "
        "VALUES (?, ?, ?, ?, ?)",
        (course["id"], "越界", "../outside.txt", "outside.txt", 1),
    )
    connection.commit()
    connection.close()
    outside.write_text("private", encoding="utf-8")

    response = client.get("/接口/资料/1/下载")
    assert response.status_code == 404
    assert outside.read_text(encoding="utf-8") == "private"


def test_upload_uses_configured_size_limit_and_cleans_file(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSEBOX_MAX_FILE_SIZE", "4")

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/api/courses", json={"name": "course"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "large"},
        files={"file": ("large.txt", b"12345", "text/plain")},
    )

    assert response.status_code == 413
    assert not list((tmp_path / "uploads").glob("*"))


def test_file_delete_restores_file_when_transaction_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_dir))

    from app.api import files as files_api
    from app.db import init_db

    init_db()
    client = TestClient(app, raise_server_exceptions=False)
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "资料回滚课程"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "资料"},
        files={"file": ("file-rollback.txt", b"file-rollback", "text/plain")},
    )
    file_id = upload.json()["id"]
    stored_file = next(upload_dir.glob("*"))

    def fail_audit(*args, **kwargs):
        raise RuntimeError("forced transaction failure")

    original_record_audit = files_api.record_audit
    monkeypatch.setattr(files_api, "record_audit", fail_audit)
    response = client.delete(f"/接口/资料/{file_id}")

    assert response.status_code == 500
    assert stored_file.read_bytes() == b"file-rollback"
    monkeypatch.setattr(files_api, "record_audit", original_record_audit)
    assert client.get(f"/接口/资料/{file_id}/下载").content == b"file-rollback"


def test_duplicate_file_is_rejected_and_file_metadata_is_returned(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "课程"}).json()
    payload = {"title": "讲义"}
    first = client.post(
        f"/接口/课程/{course['id']}/资料",
        data=payload,
        files={"file": ("a.txt", b"same content", "text/plain")},
    )
    second = client.post(
        f"/接口/课程/{course['id']}/资料",
        data=payload,
        files={"file": ("b.txt", b"same content", "text/plain")},
    )
    assert first.status_code == 201
    assert first.json()["mime_type"] == "text/plain"
    assert len(first.json()["sha256"]) == 64
    assert first.json()["status"] == "approved"
    assert second.status_code == 409
    assert len(list((tmp_path / "uploads").glob("*"))) == 1


def test_file_pagination_and_search_pagination(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "算法"}).json()
    for index in range(3):
        response = client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": f"算法资料 {index}"},
            files={"file": (f"file{index}.txt", f"content {index}".encode(), "text/plain")},
        )
        assert response.status_code == 201

    files = client.get(
        f"/接口/课程/{course['id']}/资料", params={"page": 2, "page_size": 2}
    )
    assert files.status_code == 200
    assert files.json()["total"] == 3
    assert files.json()["total_pages"] == 2
    assert len(files.json()["items"]) == 1

    search = client.get("/接口/搜索", params={"q": "算法", "page_size": 2})
    assert search.status_code == 200
    assert search.json()["total"] == 3
    assert len(search.json()["items"]) == 2


def test_old_database_is_migrated_with_search_index(tmp_path, monkeypatch):
    import sqlite3

    from app.db import init_db

    database = tmp_path / "old.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            college TEXT,
            semester TEXT
        );
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            size INTEGER NOT NULL,
            upload_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );
        INSERT INTO courses (name) VALUES ('旧课程');
        INSERT INTO files (course_id, title, filename, original_name, size)
        VALUES (1, '旧资料', 'old.txt', '旧资料.txt', 3);
        """
    )
    connection.commit()
    init_db(connection)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(files)")}
    assert {"mime_type", "sha256", "status"} <= columns
    monkeypatch.setenv("COURSEBOX_DB", str(database))
    client = create_client()
    response = client.get("/接口/搜索", params={"q": "旧资料"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    connection.close()


def test_my_uploads_listing_and_withdraw(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "我的上传课程"}).json()
    assert client.post(
        "/接口/用户",
        json={"username": "mine", "password": "mine-pass", "role": "uploader"},
    ).status_code == 201
    assert client.post(
        "/接口/用户",
        json={"username": "other", "password": "other-pass", "role": "uploader"},
    ).status_code == 201

    # 未登录访问被拒绝（此时 client 已登录管理员，需另开一个会话）。
    anonymous = create_client()
    assert anonymous.get("/接口/我的资料").status_code == 401

    worker = create_client()
    login_user(worker, "mine", "mine-pass")
    assert worker.get("/接口/我的资料").json()["total"] == 0

    pending = worker.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审核讲义"},
        files={"file": ("pending-notes.txt", b"pending-notes", "text/plain")},
    ).json()
    approved = worker.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审核习题"},
        files={"file": ("pending-exercises.txt", b"pending-exercises", "text/plain")},
    ).json()
    assert client.patch(
        f"/接口/资料/{approved['id']}/审核", json={"status": "approved"}
    ).status_code == 200

    body = worker.get("/接口/我的资料").json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {pending["id"], approved["id"]}
    first = body["items"][0]
    assert first["course"]["name"] == "我的上传课程"
    assert first["course_id"] == course["id"]
    assert first["uploaded_by"] == worker.get("/接口/当前用户").json()["id"]
    # 「我的资料」不按关键词检索，所以永远没有「命中」提示。
    assert first["matched_fields"] == []

    # 状态筛选。
    only_pending = worker.get("/接口/我的资料", params={"状态": "pending"}).json()
    assert only_pending["total"] == 1
    assert only_pending["items"][0]["id"] == pending["id"]
    only_approved = worker.get("/接口/我的资料", params={"状态": "approved"}).json()
    assert only_approved["total"] == 1
    assert only_approved["items"][0]["id"] == approved["id"]
    assert worker.get("/接口/我的资料", params={"状态": "rejected"}).json()["total"] == 0
    assert worker.get("/接口/我的资料", params={"状态": "bogus"}).status_code == 422

    # 别人看不到我的上传。
    stranger = create_client()
    login_user(stranger, "other", "other-pass")
    assert stranger.get("/接口/我的资料").json()["total"] == 0

    # 撤回待审核资料后列表减少，课程页也不再可见。
    assert worker.delete(f"/接口/资料/{pending['id']}").status_code == 204
    assert worker.get("/接口/我的资料").json()["total"] == 1
    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 1


def test_file_preview_endpoint(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "预览课程"}).json()

    def upload(title, filename, payload):
        response = client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": title},
            files={"file": (filename, payload, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    picture = upload("示意图", "示意图.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    document = upload("讲义", "lecture.pdf", b"%PDF-1.4\n%%EOF")
    archive = upload("压缩包", "bundle.zip", b"PK\x03\x04")

    preview = client.get(f"/接口/资料/{picture['id']}/预览")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.headers["x-content-type-options"] == "nosniff"
    assert preview.content.startswith(b"\x89PNG")

    pdf = client.get(f"/接口/资料/{document['id']}/预览")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")

    # 不允许内联预览的类型直接 415，避免把可执行内容塞进浏览器。
    unsupported = client.get(f"/接口/资料/{archive['id']}/预览")
    assert unsupported.status_code == 415
    assert "不支持在线预览" in unsupported.json()["error"]["message"]
    assert client.get("/接口/资料/99999/预览").status_code == 404

    # 待审核资料只对上传者本人和管理员可见。
    assert client.post(
        "/接口/用户",
        json={"username": "owner", "password": "owner-pass", "role": "uploader"},
    ).status_code == 201
    assert client.post(
        "/接口/用户",
        json={"username": "stranger", "password": "stranger-pass", "role": "uploader"},
    ).status_code == 201

    owner = create_client()
    login_user(owner, "owner", "owner-pass")
    pending = owner.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审草稿"},
        files={"file": ("draft.png", b"\x89PNG\r\n\x1a\n" + b"1" * 32, "image/png")},
    ).json()
    assert pending["status"] == "pending"

    stranger = create_client()
    login_user(stranger, "stranger", "stranger-pass")
    assert stranger.get(f"/接口/资料/{pending['id']}/预览").status_code == 404
    anonymous = create_client()
    assert anonymous.get(f"/接口/资料/{pending['id']}/预览").status_code == 404
    assert owner.get(f"/接口/资料/{pending['id']}/预览").status_code == 200
    assert client.get(f"/接口/资料/{pending['id']}/预览").status_code == 200

    # 预览行为同样写审计日志。
    import sqlite3

    connection = sqlite3.connect(tmp_path / "test.db")
    actions = [
        row[0]
        for row in connection.execute(
            "SELECT action FROM audit_logs WHERE entity_type = 'file' AND action = 'preview'"
        )
    ]
    # 预览行为同样写审计日志：上面共 4 次成功预览。
    assert len(actions) == 4
    connection.close()


def test_upload_blocked_when_course_quota_is_full(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_MAX_COURSE_BYTES", "5")
    client = quota_client(tmp_path, monkeypatch)
    course = client.post("/接口/课程", json={"name": "quota"}).json()

    first = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "第一份"},
        files={"file": ("a.txt", b"12345", "text/plain")},
    )
    assert first.status_code == 201

    over = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "超出配额"},
        files={"file": ("b.txt", b"1", "text/plain")},
    )
    assert over.status_code == 413
    assert "课程资料总量已达上限" in over.json()["error"]["message"]
    # 被拒绝的上传不能留下孤儿文件。
    assert len(list((tmp_path / "uploads").glob("*"))) == 1


def test_upload_blocked_when_site_quota_is_full(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_MAX_TOTAL_BYTES", "5")
    client = quota_client(tmp_path, monkeypatch)
    first_course = client.post("/接口/课程", json={"name": "A"}).json()
    second_course = client.post("/接口/课程", json={"name": "B"}).json()

    assert client.post(
        f"/接口/课程/{first_course['id']}/资料",
        data={"title": "A 的资料"},
        files={"file": ("a.txt", b"12345", "text/plain")},
    ).status_code == 201

    over = client.post(
        f"/接口/课程/{second_course['id']}/资料",
        data={"title": "B 的资料"},
        files={"file": ("b.txt", b"1", "text/plain")},
    )
    assert over.status_code == 413
    assert "站点资料总量已达上限" in over.json()["error"]["message"]


def test_upload_blocked_when_disk_space_is_low(tmp_path, monkeypatch):
    # 把最小剩余空间设成 1 PB，必然触发磁盘保护。
    monkeypatch.setenv("COURSEBOX_MIN_FREE_SPACE", str(10**15))
    client = quota_client(tmp_path, monkeypatch)
    course = client.post("/接口/课程", json={"name": "disk"}).json()

    blocked = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "磁盘不足"},
        files={"file": ("a.txt", b"1", "text/plain")},
    )
    assert blocked.status_code == 413
    assert "磁盘空间不足" in blocked.json()["error"]["message"]
    assert not list((tmp_path / "uploads").glob("*"))


def test_file_edit_optimistic_lock(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "并发资料"}).json()
    file = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "原名"},
        files={"file": ("a.txt", b"x", "text/plain")},
    ).json()
    assert file["version"] == 1

    ok = client.patch(f"/接口/资料/{file['id']}", json={"title": "第一次", "version": 1})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    conflict = client.patch(
        f"/接口/资料/{file['id']}", json={"title": "回退", "version": 1}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"

    # 不传版本号仍然可用（后写覆盖）。
    assert client.patch(
        f"/接口/资料/{file['id']}", json={"title": "无版本"}
    ).status_code == 200


def test_upload_rejects_executable_content(tmp_path, monkeypatch):
    """扩展名与 MIME 都能伪造，内容以可执行文件头开头的一律拒绝。"""

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "伪装课程"}).json()

    fake = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "伪装成 PDF"},
        files={"file": ("fake.pdf", b"MZ\x90\x00" + b"x" * 200, "application/pdf")},
    )
    assert fake.status_code == 415
    assert "可执行" in fake.json()["error"]["message"]
    # 被拒后不留孤儿文件。
    assert not list((tmp_path / "uploads").glob("*"))

    # 正常 PDF 仍然可以上传。
    ok = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "真 PDF"},
        files={"file": ("real.pdf", b"%PDF-1.4\n%content", "application/pdf")},
    )
    assert ok.status_code == 201


def test_per_user_upload_quota(tmp_path, monkeypatch):
    """按上传者的总量上限：一个人占满自己的额度后不能再传，但不影响别人。"""

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSEBOX_MAX_USER_BYTES", "1000")

    from app.db import init_db

    init_db()
    login_admin(client)
    first = client.post("/接口/课程", json={"name": "课程甲"}).json()
    second = client.post("/接口/课程", json={"name": "课程乙"}).json()

    assert client.post(
        f"/接口/课程/{first['id']}/资料",
        data={"title": "第一批"},
        files={"file": ("a.txt", b"x" * 800, "text/plain")},
    ).status_code == 201

    quota = client.get(f"/接口/课程/{second['id']}/配额").json()
    assert quota["user_limit"] == 1000
    assert quota["user_used"] == 800
    assert quota["user_remaining"] == 200

    blocked = client.post(
        f"/接口/课程/{second['id']}/资料",
        data={"title": "超限"},
        files={"file": ("b.txt", b"y" * 800, "text/plain")},
    )
    assert blocked.status_code == 413
    assert "上传总量" in blocked.json()["error"]["message"]

    # 另一个上传者的额度独立，不受影响。
    client.post(
        "/接口/用户",
        json={"username": "quota2", "password": "quota2-pass", "role": "uploader"},
    )
    other = create_client()
    login_user(other, "quota2", "quota2-pass")
    assert other.post(
        f"/接口/课程/{second['id']}/资料",
        data={"title": "别人"},
        files={"file": ("c.txt", b"z" * 800, "text/plain")},
    ).status_code == 201
