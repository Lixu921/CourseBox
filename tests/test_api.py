import logging
from urllib.parse import unquote

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
    chinese_script = client.get("/\u8d44\u6e90/\u811a\u672c.js")
    chinese_style = client.get("/\u8d44\u6e90/\u6837\u5f0f.css")

    assert homepage.status_code == 200
    assert 'id="search-form"' in homepage.text
    assert course_page.status_code == 200
    assert 'id="upload-form"' in course_page.text
    assert chinese_script.status_code == 200
    assert chinese_style.status_code == 200
    assert 'id="login-form"' in homepage.text
    assert 'id="admin-course-panel"' in homepage.text
    assert 'id="upload-progress"' in course_page.text
    assert 'id="file-selection"' in course_page.text


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
        "INSERT INTO files (course_id, title, filename, original_name, size) VALUES (?, ?, ?, ?, ?)",
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
