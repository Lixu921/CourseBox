import logging
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.main import app


def create_client() -> TestClient:
    return TestClient(app)


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/接口/登录", json={"username": "admin", "password": "admin12345"}
    )
    assert response.status_code == 200, response.text


def login_user(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/接口/登录", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_check(tmp_path, monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "health.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    response = client.get("/\u63a5\u53e3/\u5065\u5eb7")

    assert response.status_code == 200
    assert response.json()["app"] == "CourseBox"
    assert response.json()["status"] == "ok"
    assert {"database", "uploads", "disk"} == set(response.json()["checks"])
    assert all(item["status"] == "ok" for item in response.json()["checks"].values())


def test_health_check_reports_unusable_upload_path(tmp_path, monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    database = tmp_path / "health.db"
    upload_path = tmp_path / "upload-file"
    upload_path.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("COURSEBOX_DB", str(database))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_path))

    from app.db import init_db

    init_db()
    response = client.get("/接口/健康")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["uploads"]["status"] == "error"


def test_pages_are_available():
    client = create_client()
    homepage = client.get("/")
    course_page = client.get("/\u8bfe\u7a0b")
    ascii_course_page = client.get("/course?id=1")
    chinese_script = client.get("/\u8d44\u6e90/\u811a\u672c.js")
    chinese_style = client.get("/\u8d44\u6e90/\u6837\u5f0f.css")
    static_script = client.get("/static/app.js")
    static_style = client.get("/static/style.css")

    assert homepage.status_code == 200
    assert 'id="search-form"' in homepage.text
    assert course_page.status_code == 200
    assert ascii_course_page.status_code == 200
    assert 'id="upload-form"' in course_page.text
    assert chinese_script.status_code == 200
    assert chinese_style.status_code == 200
    assert static_script.status_code == 200
    assert static_style.status_code == 200
    assert 'href="/static/style.css"' in homepage.text
    assert 'src="/static/app.js"' in homepage.text
    assert 'id="login-form"' in homepage.text
    assert 'id="admin-course-panel"' in homepage.text
    assert 'id="admin-user-panel"' in homepage.text
    assert 'id="user-list"' in homepage.text
    assert 'id="upload-progress"' in course_page.text
    assert 'id="file-selection"' in course_page.text
    assert 'href="#top"' in homepage.text
    assert 'href="#top"' in course_page.text


def test_create_and_list_courses(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    create_response = client.post(
        "/\u63a5\u53e3/\u8bfe\u7a0b",
        json={"name": "Data Structures", "college": "Computer Science", "semester": "2026"},
    )

    assert create_response.status_code == 201
    course = create_response.json()
    assert course["name"] == "Data Structures"

    list_response = client.get("/\u63a5\u53e3/\u8bfe\u7a0b")

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert any(item["id"] == course["id"] for item in list_response.json()["items"])


def test_course_name_is_required():
    client = create_client()
    login_admin(client)
    response = client.post("/\u63a5\u53e3/\u8bfe\u7a0b", json={"name": ""})

    assert response.status_code == 422


def test_text_fields_are_trimmed_and_have_length_limits(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    created = client.post(
        "/接口/课程",
        json={"name": "  数据结构  ", "college": "  计算机学院  ", "semester": "  2026 春  "},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "数据结构"
    assert created.json()["college"] == "计算机学院"
    assert created.json()["semester"] == "2026 春"

    blank_optional = client.patch(
        f"/接口/课程/{created.json()['id']}",
        json={"college": "   ", "semester": "   "},
    )
    assert blank_optional.status_code == 200
    assert blank_optional.json()["college"] is None
    assert blank_optional.json()["semester"] is None
    assert client.patch(
        f"/接口/课程/{created.json()['id']}", json={"name": None}
    ).status_code == 422
    assert client.post("/接口/课程", json={"name": "x" * 201}).status_code == 422
    assert client.post(
        "/接口/课程", json={"name": "x", "college": "y" * 121}
    ).status_code == 422
    assert client.post("/接口/课程", json={"name": 123}).status_code == 422


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


def test_api_errors_have_uniform_shape():
    client = create_client()
    response = client.get("/接口/课程/999999")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "课程不存在"
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "课程不存在"
    assert body["error"]["request_id"] == response.headers["x-request-id"]

    # 路由未命中的 404 也必须走同一套错误结构，不能退回框架默认的 {"detail": "Not Found"}。
    unmatched = client.get("/不存在的路径")
    assert unmatched.status_code == 404
    unmatched_body = unmatched.json()
    assert unmatched_body["error"]["code"] == "not_found"
    assert unmatched_body["error"]["message"] == "Not Found"
    assert unmatched_body["error"]["request_id"] == unmatched.headers["x-request-id"]


def test_request_id_and_structured_log(caplog):
    client = create_client()
    with caplog.at_level(logging.INFO, logger="coursebox"):
        response = client.get("/接口/健康", headers={"X-Request-ID": "test-request-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request-1"
    record = next(record for record in caplog.records if record.name == "coursebox")
    assert record.event == "http_request"
    assert record.request_id == "test-request-1"
    assert record.method == "GET"
    assert record.path == "/接口/健康"
    assert record.status_code == 200
    assert record.duration_ms >= 0


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


def test_configuration_values_are_trimmed_and_invalid_values_fall_back(monkeypatch):
    from app.config import (
        DEFAULT_MAX_FILE_SIZE,
        allowed_extensions,
        database_path,
        max_file_size,
        uploads_path,
    )

    monkeypatch.setenv("COURSEBOX_DB", "  custom.db  ")
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", "  custom-uploads  ")
    monkeypatch.setenv("COURSEBOX_MAX_FILE_SIZE", "not-a-number")
    monkeypatch.setenv("COURSEBOX_ALLOWED_EXTENSIONS", " TXT, .PDF,  ")

    assert database_path().name == "custom.db"
    assert uploads_path().name == "custom-uploads"
    assert max_file_size() == DEFAULT_MAX_FILE_SIZE
    assert allowed_extensions() == {".txt", ".pdf"}

    monkeypatch.setenv("COURSEBOX_ALLOWED_EXTENSIONS", " ,  ")
    assert ".txt" in allowed_extensions()


def test_chinese_routes_are_the_only_public_routes(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post(
        "/\u63a5\u53e3/\u8bfe\u7a0b", json={"name": "Chinese Route Test"}
    ).json()
    upload = client.post(
        f"/\u63a5\u53e3/\u8bfe\u7a0b/{course['id']}/\u8d44\u6599",
        data={"title": "Test Resource"},
        files={"file": ("test.txt", b"chinese-route", "text/plain")},
    )

    assert client.get("/\u63a5\u53e3/\u8bfe\u7a0b").status_code == 200
    assert upload.status_code == 201
    file_id = upload.json()["id"]
    assert client.get(
        f"/\u63a5\u53e3/\u8bfe\u7a0b/{course['id']}/\u8d44\u6599"
    ).status_code == 200
    assert client.get(
        f"/\u63a5\u53e3/\u8d44\u6599/{file_id}/\u4e0b\u8f7d"
    ).status_code == 200
    search = client.get(
        "/\u63a5\u53e3/\u641c\u7d22", params={"q": "Chinese Route Test"}
    )
    assert search.status_code == 200

    assert client.get("/static/app.js").status_code == 200
    assert client.get("/\u8d44\u6e90/app.js").status_code == 404
    assert client.get("/course.html").status_code == 404

    documented_paths = client.get("/\u63a5\u53e3\u5b9a\u4e49").json()["paths"]
    assert all(not path.startswith("/api/") for path in documented_paths)
    assert all("files" not in path and "search" not in path for path in documented_paths)
    assert all("course_id" not in path and "file_id" not in path for path in documented_paths)
    assert all("Course" not in str(item) for item in documented_paths.values())


def test_course_pagination_and_detail(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    for name in ("课程一", "课程二", "课程三"):
        assert client.post("/接口/课程", json={"name": name}).status_code == 201

    response = client.get("/接口/课程", params={"page": 2, "page_size": 2})
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": 1, "name": "课程一", "college": None, "semester": None}],
        "total": 3,
        "page": 2,
        "page_size": 2,
        "total_pages": 2,
    }

    detail = client.get("/接口/课程/3")
    assert detail.status_code == 200
    assert detail.json()["name"] == "课程三"
    assert detail.json()["file_count"] == 0
    assert client.get("/接口/课程/999999").status_code == 404


def test_course_and_file_can_be_updated_and_deleted_with_disk_cleanup(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_dir))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "旧课程"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "旧标题"},
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]
    stored_files = list(upload_dir.glob("*"))
    assert len(stored_files) == 1

    updated_course = client.patch(
        f"/接口/课程/{course['id']}",
        json={"name": "新课程", "semester": "2026"},
    )
    assert updated_course.status_code == 200
    assert updated_course.json()["name"] == "新课程"
    assert updated_course.json()["semester"] == "2026"
    updated_file = client.patch(
        f"/接口/资料/{file_id}", json={"title": "新标题"}
    )
    assert updated_file.status_code == 200
    assert updated_file.json()["title"] == "新标题"

    assert client.delete(f"/接口/课程/{course['id']}").status_code == 204
    assert client.get(f"/接口/资料/{file_id}/下载").status_code == 404
    assert not list(upload_dir.glob("*"))
    assert client.delete(f"/接口/课程/{course['id']}").status_code == 404


def test_course_delete_restores_file_when_transaction_fails(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(upload_dir))

    from app.api import courses as courses_api
    from app.db import init_db

    init_db()
    client = TestClient(app, raise_server_exceptions=False)
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "待回滚课程"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待回滚资料"},
        files={"file": ("rollback.txt", b"rollback-content", "text/plain")},
    )
    assert upload.status_code == 201
    stored_file = next(upload_dir.glob("*"))

    def fail_audit(*args, **kwargs):
        raise RuntimeError("forced transaction failure")

    original_record_audit = courses_api.record_audit
    monkeypatch.setattr(courses_api, "record_audit", fail_audit)
    response = client.delete(f"/接口/课程/{course['id']}")

    assert response.status_code == 500
    assert stored_file.read_bytes() == b"rollback-content"
    monkeypatch.setattr(courses_api, "record_audit", original_record_audit)
    assert client.get(f"/接口/课程/{course['id']}").status_code == 200
    connection = sqlite3.connect(tmp_path / "test.db")
    assert connection.execute("SELECT COUNT(*) FROM file_deletion_journal").fetchone()[0] == 0
    connection.close()


def test_course_delete_reports_staging_failure_without_masking_error(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.api import courses as courses_api
    from app.db import init_db

    init_db()
    client = TestClient(app, raise_server_exceptions=False)
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "暂存失败课程"}).json()

    def fail_staging(*args, **kwargs):
        raise OSError("forced staging failure")

    monkeypatch.setattr(courses_api, "stage_stored_files", fail_staging)
    response = client.delete(f"/接口/课程/{course['id']}")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert client.get(f"/接口/课程/{course['id']}").status_code == 200


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


def searchable_client(tmp_path, monkeypatch):
    """建库、建课、上传一份中文名资料，返回 (client, course_id)。"""

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "数据结构期中复习"},
        files={"file": ("数据结构期中.pdf", b"hello", "application/pdf")},
    )
    assert uploaded.status_code == 201
    return client, course["id"]


def test_search_matches_chinese_substring(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # trigram 分词器支持任意位置的中文子串，不再要求从词首开始。
    for keyword in ("数据结构", "据结构", "构期中", "期中复习"):
        response = client.get("/接口/搜索", params={"q": keyword})
        assert response.status_code == 200, keyword
        assert response.json()["total"] == 1, keyword


def test_short_keyword_falls_back_to_like(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # 少于 3 个字符无法进入 trigram 索引，必须靠 LIKE 兜底。
    assert client.get("/接口/搜索", params={"q": "数据"}).json()["total"] == 1
    assert client.get("/接口/搜索", params={"q": "期中"}).json()["total"] == 1
    assert client.get("/接口/搜索", params={"q": "数学"}).json()["total"] == 0


def test_multi_term_search_requires_all_terms(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    assert client.get(
        "/接口/搜索", params={"q": "数据结构 期中"}
    ).json()["total"] == 1
    assert client.get(
        "/接口/搜索", params={"q": "数据结构 高数"}
    ).json()["total"] == 0


def test_search_escapes_like_wildcards(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # 未转义时 "%中" 会变成通配符匹配到所有资料。
    assert client.get("/接口/搜索", params={"q": "%中"}).json()["total"] == 0
    assert client.get("/接口/搜索", params={"q": "_结构"}).json()["total"] == 0


def test_search_matches_course_name(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # 资料标题里没有“高等数学”，但课程名匹配同样应该命中。
    course = client.post("/接口/课程", json={"name": "高等数学"}).json()
    client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "第一章"},
        files={"file": ("chapter1.pdf", b"x", "application/pdf")},
    )

    response = client.get("/接口/搜索", params={"q": "高等数学"})
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["course"]["name"] == "高等数学"


def test_search_query_plan_uses_fts_index(tmp_path, monkeypatch):
    import sqlite3

    client, _ = searchable_client(tmp_path, monkeypatch)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.api.files import build_search_filter

    where, params = build_search_filter("数据结构", use_fts=True)
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        plan = "\n".join(
            row[-1]
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT f.id FROM files AS f "
                "JOIN courses AS c ON c.id = f.course_id "
                f"WHERE f.status = 'approved' AND ({where})",
                params,
            )
        )
    finally:
        connection.close()

    # INDEX 0:M* 表示 MATCH 约束生效；INDEX 0:= 表示退化成整表扫描。
    assert "files_fts VIRTUAL TABLE INDEX 0:M" in plan, plan
    assert "INDEX 0:=" not in plan, plan


def test_legacy_fts_index_is_rebuilt_with_trigram(tmp_path, monkeypatch):
    import sqlite3

    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, college TEXT, semester TEXT
        );
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL, filename TEXT NOT NULL, original_name TEXT NOT NULL,
            size INTEGER NOT NULL, upload_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE files_fts USING fts5(
            title, original_name, content='files', content_rowid='id'
        );
        INSERT INTO courses (name) VALUES ('数据结构');
        INSERT INTO files (course_id, title, filename, original_name, size)
        VALUES (1, '数据结构期中复习', 'old.pdf', '数据结构期中.pdf', 3);
        """
    )
    connection.commit()

    from app.db import init_db

    init_db(connection)
    index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'files_fts'"
    ).fetchone()[0]
    assert "trigram" in index_sql.lower()
    connection.close()

    monkeypatch.setenv("COURSEBOX_DB", str(database))
    client = create_client()
    # 旧索引用的是默认分词器，中文子串命中不了；重建之后必须能搜到。
    assert client.get("/接口/搜索", params={"q": "据结构"}).json()["total"] == 1


def quota_client(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    return client


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


def test_maintenance_module_runs(tmp_path, monkeypatch, capsys):
    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_AUDIT_RETENTION_DAYS", "1")

    from app import maintenance
    from app.db import init_db

    init_db()
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.execute(
        "INSERT INTO audit_logs (actor_id, action, entity_type, created_at)"
        " VALUES (NULL, 'stale', 'file', datetime('now', '-10 days'))"
    )
    connection.commit()
    connection.close()

    assert maintenance.main() == 0
    assert "已清理 1 条" in capsys.readouterr().out


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
