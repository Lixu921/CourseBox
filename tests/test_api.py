import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.db import reset_initialized_databases
from app.main import app
from app.ratelimit import reset_rate_limits


def create_client() -> TestClient:
    # 限流按客户端 IP 计数，而所有测试都来自同一个 TestClient 主机；
    # 建表缓存按数据库路径记忆。两者都清空，测试之间才不会互相影响。
    reset_rate_limits()
    reset_initialized_databases()
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
    assert 'id="search-filters"' in homepage.text
    assert 'id="search-course"' in homepage.text
    assert 'id="search-sort"' in homepage.text
    assert course_page.status_code == 200
    assert ascii_course_page.status_code == 200
    assert 'id="upload-form"' in course_page.text
    assert chinese_script.status_code == 200
    assert chinese_style.status_code == 200
    assert static_script.status_code == 200
    assert static_style.status_code == 200
    # 页面引用带内容哈希版本号的中文静态路由，便于长期缓存后强制刷新。
    assert 'href="/资源/样式.css?v=' in homepage.text
    assert 'src="/资源/脚本.js?v=' in homepage.text
    assert 'href="/资源/图标.svg"' in homepage.text
    assert 'id="login-form"' in homepage.text
    assert 'id="admin-course-panel"' in homepage.text
    assert 'id="admin-user-panel"' in homepage.text
    assert 'id="user-list"' in homepage.text
    assert 'id="my-uploads-panel"' in homepage.text
    assert 'id="my-uploads-list"' in homepage.text
    assert 'id="audit-panel"' in homepage.text
    assert 'id="audit-list"' in homepage.text
    assert 'id="audit-filter-action"' in homepage.text
    assert 'id="trash-panel"' in homepage.text
    assert 'id="trash-list"' in homepage.text
    assert 'id="trash-filter-keyword"' in homepage.text
    # 首页只留一个搜索框：同时搜课程和资料，结果分两组展示。
    assert 'id="course-search-form"' not in homepage.text
    assert 'id="course-list"' in homepage.text
    assert 'class="results"' in homepage.text
    assert homepage.text.count("<form id=\"search-form\"") == 1
    assert 'id="auth-hint"' in homepage.text
    assert 'id="auth-hint-login"' in homepage.text
    assert 'id="upload-progress"' in course_page.text
    assert 'id="file-selection"' in course_page.text
    assert 'id="drop-zone"' in course_page.text
    assert 'id="upload-quota"' in course_page.text
    assert 'id="upload-results"' in course_page.text
    assert 'id="preview-dialog"' in course_page.text
    assert "multiple" in course_page.text
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


def test_search_reports_matched_fields(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # 标题「数据结构期中复习」和文件名「数据结构期中.pdf」都含「期中」，课程名不含。
    hit = client.get("/接口/搜索", params={"q": "期中"}).json()["items"][0]
    assert hit["matched_fields"] == ["标题", "文件名"]

    # 三个字段都含「数据结构」，顺序按后端 SEARCHABLE_FIELDS 固定。
    hit = client.get("/接口/搜索", params={"q": "数据结构"}).json()["items"][0]
    assert hit["matched_fields"] == ["标题", "文件名", "课程名"]


def test_search_matched_fields_can_be_course_name_only(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    course = client.post("/接口/课程", json={"name": "高等数学"}).json()
    client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "第一章"},
        files={"file": ("chapter1.pdf", b"x", "application/pdf")},
    )

    # 标题和文件名都不含关键词，命中的只有课程名——这正是「命中：课程名」要解释的场景。
    hit = client.get("/接口/搜索", params={"q": "高等数学"}).json()["items"][0]
    assert hit["matched_fields"] == ["课程名"]


def test_search_without_keyword_has_no_matched_fields(tmp_path, monkeypatch):
    client, _ = searchable_client(tmp_path, monkeypatch)

    # 只按类型筛选、没有关键词时不该凭空造出「命中」提示。
    item = client.get("/接口/搜索", params={"类型": "pdf"}).json()["items"][0]
    assert item["matched_fields"] == []


def test_matched_field_labels_and_search_terms_units():
    from app.api.files import matched_field_labels, search_terms

    row = {"title": "数据结构", "original_name": "a.pdf", "course_name": "数据结构"}
    assert matched_field_labels(row, []) == []
    assert matched_field_labels(row, ["不存在的词"]) == []
    assert matched_field_labels(row, ["数据结构"]) == ["标题", "课程名"]

    # 拆词规则要和前端 highlight() 一致：按空白切分、去空、转小写。
    assert search_terms("  数据  结构 ") == ["数据", "结构"]
    assert search_terms("Data Structures") == ["data", "structures"]
    assert search_terms("   ") == []


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




def test_search_filters_and_sorting(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    data_structures = client.post("/接口/课程", json={"name": "数据结构"}).json()
    maths = client.post("/接口/课程", json={"name": "高等数学"}).json()

    def upload(course_id, title, filename, payload):
        response = client.post(
            f"/接口/课程/{course_id}/资料",
            data={"title": title},
            files={"file": (filename, payload, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    lecture = upload(data_structures["id"], "第一章 绪论", "lecture-01.pdf", b"a" * 10)
    exercise = upload(data_structures["id"], "习题答案", "exercise.pdf", b"b" * 200)
    slides = upload(maths["id"], "极限与连续", "chapter1.pptx", b"c" * 100)

    # 既没有关键词也没有筛选条件时不做全表扫描。
    assert client.get("/接口/搜索").json()["total"] == 0

    # 只有筛选条件、没有关键词时也要能列出资料。
    by_course = client.get("/接口/搜索", params={"课程编号": maths["id"]}).json()
    assert by_course["total"] == 1
    assert by_course["items"][0]["id"] == slides["id"]

    by_type = client.get("/接口/搜索", params={"类型": "pdf"}).json()
    assert {item["id"] for item in by_type["items"]} == {lecture["id"], exercise["id"]}
    assert client.get("/接口/搜索", params={"类型": ".PDF"}).json()["total"] == 2
    assert client.get("/接口/搜索", params={"类型": "pptx"}).json()["total"] == 1
    assert client.get("/接口/搜索", params={"类型": "zip"}).json()["total"] == 0

    # 课程 + 类型组合。
    combined = client.get(
        "/接口/搜索", params={"课程编号": data_structures["id"], "类型": "pdf"}
    ).json()
    assert combined["total"] == 2

    # 关键词与筛选条件同时生效（AND）。
    assert client.get(
        "/接口/搜索", params={"q": "习题", "类型": "pdf"}
    ).json()["total"] == 1
    assert client.get(
        "/接口/搜索", params={"q": "习题", "类型": "pptx"}
    ).json()["total"] == 0

    # 排序：用起始时间作为兜底筛选，保证能列出全部三份资料。
    base = {"起始时间": "2000-01-01"}
    assert client.get("/接口/搜索", params=base).json()["total"] == 3
    by_size = client.get("/接口/搜索", params={**base, "排序": "size"}).json()["items"]
    assert [item["size"] for item in by_size] == [200, 100, 10]
    by_name = client.get("/接口/搜索", params={**base, "排序": "name"}).json()["items"]
    assert [item["title"] for item in by_name] == sorted(
        ["第一章 绪论", "习题答案", "极限与连续"]
    )
    newest = client.get("/接口/搜索", params={**base, "排序": "newest"}).json()["items"]
    assert [item["id"] for item in newest] == [slides["id"], exercise["id"], lecture["id"]]
    oldest = client.get("/接口/搜索", params={**base, "排序": "oldest"}).json()["items"]
    assert [item["id"] for item in oldest] == [lecture["id"], exercise["id"], slides["id"]]
    assert client.get("/接口/搜索", params={"排序": "bogus"}).status_code == 422

    # 时间范围与参数校验。
    assert client.get(
        "/接口/搜索", params={"起始时间": "2999-01-01"}
    ).json()["total"] == 0
    assert client.get(
        "/接口/搜索", params={"结束时间": "2000-01-01"}
    ).json()["total"] == 0
    assert client.get(
        "/接口/搜索", params={"起始时间": "2020-01-01", "结束时间": "2019-01-01"}
    ).status_code == 422
    assert client.get("/接口/搜索", params={"起始时间": "not-a-date"}).status_code == 422


def test_search_sort_accepts_chinese_aliases(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()

    def upload(title, filename, payload):
        response = client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": title},
            files={"file": (filename, payload, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    small = upload("甲", "a.pdf", b"a" * 10)
    large = upload("乙", "b.pdf", b"b" * 300)

    # 用起始时间兜底，保证没有关键词时也能列出全部资料。
    base = {"起始时间": "2000-01-01"}

    def items(sort_value):
        response = client.get("/接口/搜索", params={**base, "排序": sort_value})
        assert response.status_code == 200, response.text
        return response.json()["items"]

    # 中文别名与英文枚举结果一致。
    assert [item["id"] for item in items("大小")] == [
        item["id"] for item in items("size")
    ]
    assert [item["size"] for item in items("大小")] == [300, 10]

    assert [item["id"] for item in items("最早")] == [
        item["id"] for item in items("oldest")
    ]
    assert [item["id"] for item in items("最早")] == [small["id"], large["id"]]

    assert [item["id"] for item in items("最新")] == [
        item["id"] for item in items("newest")
    ]
    assert [item["id"] for item in items("最新")] == [large["id"], small["id"]]

    assert [item["title"] for item in items("标题")] == sorted(["甲", "乙"])

    # 白名单之外的值依然拒绝。
    assert client.get("/接口/搜索", params={"排序": "最大"}).status_code == 422


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


def test_backup_creates_and_rotates_backups(tmp_path, monkeypatch, capsys):
    import zipfile

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app import backup
    from app.db import init_db

    init_db()
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "讲义.txt").write_text("内容", encoding="utf-8")

    destination = tmp_path / "backups"
    stamps = ("20260101-010101", "20260102-020202", "20260103-030303")
    results = []
    for stamp in stamps:
        result = backup.run(destination, keep=2, stamp=stamp)
        # 每份备份在生成时都必须存在且通过完整性校验（旧备份随后会被轮转清理）。
        assert result.database.is_file()
        assert backup.integrity_ok(result.database)
        results.append(result)

    assert results[0].removed == []
    # 第三次备份后，最旧的一组（数据库 + 上传归档）被清理。
    assert sorted(path.name for path in results[-1].removed) == [
        "coursebox-20260101-010101.db",
        "uploads-20260101-010101.zip",
    ]
    assert sorted(path.name for path in destination.iterdir()) == [
        "coursebox-20260102-020202.db",
        "coursebox-20260103-030303.db",
        "uploads-20260102-020202.zip",
        "uploads-20260103-030303.zip",
    ]

    with zipfile.ZipFile(destination / "uploads-20260103-030303.zip") as archive:
        assert archive.namelist() == ["讲义.txt"]

    # keep=0 表示全部保留。
    backup.run(destination, keep=0, stamp="20260104-040404")
    assert len(list(destination.iterdir())) == 6

    # 命令行入口：默认保留最近 1 组，并打印清理结果。
    assert backup.main(["--destination", str(destination), "--keep", "1"]) == 0
    output = capsys.readouterr().out
    assert "备份完成" in output
    assert "已清理" in output
    assert len(list(destination.iterdir())) == 2


def test_backup_skips_uploads_and_reports_missing_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app import backup
    from app.db import init_db

    init_db()
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "uploads" / "note.txt").write_text("hi", encoding="utf-8")

    destination = tmp_path / "backups"
    result = backup.run(
        destination, include_uploads=False, stamp="20260101-010101"
    )
    assert result.uploads is None
    assert [path.name for path in destination.iterdir()] == [
        "coursebox-20260101-010101.db"
    ]

    # 上传目录为空时跳过打包，不算失败。
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "empty-uploads"))
    assert backup.main(
        ["--destination", str(destination), "--keep", "0"]
    ) == 0
    assert "已跳过打包" in capsys.readouterr().out

    # 数据库不存在时返回 1 并给出原因。
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "missing.db"))
    assert backup.main(["--destination", str(destination)]) == 1
    assert "备份失败" in capsys.readouterr().err


def test_backup_script_entrypoint_is_importable():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "backup.py"
    spec = importlib.util.spec_from_file_location("coursebox_backup_script", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


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


def test_course_quota_endpoint(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSEBOX_MAX_FILE_SIZE", "400")
    monkeypatch.setenv("COURSEBOX_MAX_COURSE_BYTES", "1000")
    monkeypatch.setenv("COURSEBOX_MAX_TOTAL_BYTES", "5000")

    from app.db import init_db

    init_db()

    # 未登录不给看，避免把服务器磁盘信息暴露给匿名访客。
    assert client.get("/接口/课程/1/配额").status_code == 401

    login_admin(client)
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()

    quota = client.get(f"/接口/课程/{course['id']}/配额").json()
    assert quota["max_file_size"] == 400
    assert quota["course_limit"] == 1000
    assert quota["course_used"] == 0
    assert quota["course_remaining"] == 1000
    assert quota["site_remaining"] == 5000
    # 四项上限里单文件大小最紧，所以本次允许 400 字节。
    assert quota["allowed_bytes"] == 400
    assert "400 字节" in quota["reason"]
    assert quota["disk_free"] and quota["disk_free"] > 0

    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "绪论"},
        files={"file": ("intro.pdf", b"a" * 300, "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text

    # 上传后已用与剩余要跟着变。
    after = client.get(f"/接口/课程/{course['id']}/配额").json()
    assert after["course_used"] == 300
    assert after["course_remaining"] == 700
    assert after["site_used"] == 300
    assert after["site_remaining"] == 4700

    # 课程总量耗尽时，允许字节数降到 0，并给出对应原因。
    exhausted = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "补遗"},
        files={"file": ("extra.pdf", b"b" * 300, "application/octet-stream")},
    )
    assert exhausted.status_code == 201, exhausted.text
    full = client.get(f"/接口/课程/{course['id']}/配额").json()
    assert full["course_remaining"] == 400
    assert full["allowed_bytes"] == 400

    assert client.get("/接口/课程/9999/配额").status_code == 404


def test_course_list_keyword_search(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    client.post(
        "/接口/课程",
        json={"name": "数据结构", "college": "计算机学院", "semester": "2026 秋"},
    )
    client.post(
        "/接口/课程",
        json={"name": "高等数学", "college": "数学学院", "semester": "2026 秋"},
    )
    client.post("/接口/课程", json={"name": "线性代数"})

    assert client.get("/接口/课程").json()["total"] == 3

    # 关键词分别命中课程名、学院、学期。
    assert client.get("/接口/课程", params={"关键词": "高等"}).json()["total"] == 1
    assert client.get("/接口/课程", params={"关键词": "计算机"}).json()["total"] == 1
    assert client.get("/接口/课程", params={"关键词": "2026 秋"}).json()["total"] == 2
    assert client.get("/接口/课程", params={"关键词": "不存在"}).json()["total"] == 0

    # 通配符要被转义，不能把 % 当成"匹配全部"。
    assert client.get("/接口/课程", params={"关键词": "%"}).json()["total"] == 0
    assert client.get("/接口/课程", params={"关键词": "_"}).json()["total"] == 0

    # 关键词与分页同时生效。
    paged = client.get(
        "/接口/课程", params={"关键词": "2026 秋", "page": 1, "page_size": 1}
    ).json()
    assert len(paged["items"]) == 1
    assert paged["total"] == 2
    assert paged["total_pages"] == 2


def test_database_schema_is_initialized_once_per_path(tmp_path, monkeypatch):
    """建表只在进程首次打开该库时跑一次。

    init_db 里全是 DDL 与 PRAGMA journal_mode=WAL，在新建连接上要上百毫秒；
    如果每个请求都跑一遍，单次请求会被拖慢两个数量级。
    """

    from app import db as db_module

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "once.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    create_client()

    calls: list[int] = []
    real_init_db = db_module.init_db

    def counting_init_db(connection=None):
        calls.append(1)
        return real_init_db(connection)

    monkeypatch.setattr(db_module, "init_db", counting_init_db)

    client = create_client()
    for _ in range(3):
        assert client.get("/接口/课程").status_code == 200
    assert len(calls) == 1

    # 清掉缓存后会重新初始化一次，用于确认缓存确实是按路径生效的。
    reset_initialized_databases()
    assert client.get("/接口/课程").status_code == 200
    assert len(calls) == 2


def test_security_headers_on_pages_and_static_files():
    client = create_client()

    homepage = client.get("/")
    assert homepage.status_code == 200
    assert homepage.headers["X-Content-Type-Options"] == "nosniff"
    assert homepage.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert homepage.headers["Referrer-Policy"] == "no-referrer"
    csp = homepage.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "object-src 'none'" in csp

    # 静态资源也要带兜底安全头，但 CSP 只给 HTML 页面。
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert script.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in script.headers

    # 带版本号的静态资源可长期强缓存；页面与无版本号请求必须每次校验。
    versioned = client.get("/资源/脚本.js", params={"v": "deadbeef"})
    assert versioned.status_code == 200
    assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    unversioned = client.get("/资源/脚本.js")
    assert unversioned.headers["Cache-Control"] == "no-cache"
    assert homepage.headers["Cache-Control"] == "no-cache"


def test_rate_limit_returns_429_with_request_id(monkeypatch):
    monkeypatch.setenv("COURSEBOX_RATE_LIMIT_PER_MINUTE", "5")
    client = create_client()

    for _ in range(5):
        assert client.get("/接口/课程").status_code == 200

    blocked = client.get("/接口/课程")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_requests"
    assert blocked.json()["error"]["message"] == "请求过于频繁，请稍后再试"
    assert int(blocked.headers["Retry-After"]) >= 1
    # 429 也要带 request_id 与安全头，否则线上排查会断线索（依赖中间件注册顺序）。
    assert blocked.headers["X-Request-ID"]
    assert blocked.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_rate_limit_can_be_disabled(monkeypatch):
    monkeypatch.setenv("COURSEBOX_RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("COURSEBOX_RATE_LIMIT_ENABLED", "false")
    client = create_client()

    for _ in range(4):
        assert client.get("/接口/课程").status_code == 200


def test_health_check_is_exempt_from_rate_limit(monkeypatch):
    monkeypatch.setenv("COURSEBOX_RATE_LIMIT_PER_MINUTE", "2")
    client = create_client()

    for _ in range(6):
        assert client.get("/接口/健康").status_code == 200


def test_deleted_file_goes_to_trash_and_can_be_restored(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "回收站课程"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "可回收资料"},
        files={"file": ("recycle-me.txt", b"recycle-me", "text/plain")},
    ).json()

    assert client.get("/接口/回收站").json()["total"] == 0

    # 删除只是移入回收站：课程页里消失，但磁盘文件仍在。
    assert client.delete(f"/接口/资料/{uploaded['id']}").status_code == 204
    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 0
    trash = client.get("/接口/回收站").json()
    assert trash["total"] == 1
    assert len(list(uploads.iterdir())) == 1

    item = trash["items"][0]
    assert item["id"] == uploaded["id"]
    assert item["original_name"] == "recycle-me.txt"
    assert item["course_name"] == "回收站课程"
    assert item["deleted_by_name"] == "admin"
    assert item["deleted_at"]

    # 恢复后重新可见，回收站清空。
    restored = client.post(f"/接口/回收站/{uploaded['id']}/恢复")
    assert restored.status_code == 200
    assert restored.json()["id"] == uploaded["id"]
    assert client.get("/接口/回收站").json()["total"] == 0
    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 1
    # 恢复后仍能正常下载。
    assert client.get(f"/接口/资料/{uploaded['id']}/下载").status_code == 200


def test_trash_purge_deletes_file_from_disk(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "彻底删除课程"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待彻底删除"},
        files={"file": ("purge-me.txt", b"purge-me", "text/plain")},
    ).json()

    assert client.delete(f"/接口/资料/{uploaded['id']}").status_code == 204
    assert len(list(uploads.iterdir())) == 1

    # 彻底删除后磁盘文件真的没了，也无法再恢复。
    assert client.delete(f"/接口/回收站/{uploaded['id']}").status_code == 204
    assert list(uploads.iterdir()) == []
    assert client.get("/接口/回收站").json()["total"] == 0
    assert client.post(f"/接口/回收站/{uploaded['id']}/恢复").status_code == 404
    assert client.delete(f"/接口/回收站/{uploaded['id']}").status_code == 404


def trash_client(tmp_path, monkeypatch, count=3):
    """建库、建课、上传 count 份资料并全部移入回收站，返回 (client, course, uploads, ids)。"""

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "批量回收站课程"}).json()
    ids = []
    for index in range(count):
        uploaded = client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": f"待处理资料 {index}"},
            files={"file": (f"batch-{index}.txt", f"batch-{index}".encode(), "text/plain")},
        ).json()
        assert client.delete(f"/接口/资料/{uploaded['id']}").status_code == 204
        ids.append(uploaded["id"])
    assert client.get("/接口/回收站").json()["total"] == count
    return client, course, uploads, ids


def test_trash_batch_restore(tmp_path, monkeypatch):
    client, course, uploads, ids = trash_client(tmp_path, monkeypatch)

    response = client.post("/接口/回收站/批量恢复", json={"ids": ids})
    assert response.status_code == 200
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (3, 0)
    assert all(item["ok"] for item in body["items"])

    assert client.get("/接口/回收站").json()["total"] == 0
    assert client.get(f"/接口/课程/{course['id']}/资料").json()["total"] == 3
    # 恢复后磁盘文件仍在原处。
    assert len(list(uploads.iterdir())) == 3


def test_trash_batch_purge_removes_files_from_disk(tmp_path, monkeypatch):
    client, course, uploads, ids = trash_client(tmp_path, monkeypatch)

    response = client.post("/接口/回收站/批量彻底删除", json={"ids": ids})
    assert response.status_code == 200
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (3, 0)

    assert client.get("/接口/回收站").json()["total"] == 0
    assert list(uploads.iterdir()) == []
    # 彻底删掉之后连恢复都不行了。
    assert client.post(f"/接口/回收站/{ids[0]}/恢复").status_code == 404


def test_trash_batch_reports_per_item_failures(tmp_path, monkeypatch):
    client, _, _, ids = trash_client(tmp_path, monkeypatch)

    # 一个不存在、一个已恢复过的编号混进来，不该拖垮其余几条。
    missing = max(ids) + 999
    response = client.post(
        "/接口/回收站/批量恢复", json={"ids": [ids[0], missing, ids[0]]}
    )
    assert response.status_code == 200
    body = response.json()
    # ids[0] 被去重成一条，所以总共只有 2 条结果。
    assert len(body["items"]) == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[ids[0]]["ok"] is True
    assert by_id[missing]["ok"] is False
    assert "回收站里没有这条资料" in by_id[missing]["message"]

    # 成功的恢复了、失败的没影响其他人。
    assert client.get("/接口/回收站").json()["total"] == 2


def test_trash_batch_requires_admin_and_valid_body(tmp_path, monkeypatch):
    client, _, _, ids = trash_client(tmp_path, monkeypatch)

    assert client.post(
        "/接口/用户",
        json={"username": "batch-uploader", "password": "uploader-pass", "role": "uploader"},
    ).status_code == 201
    anonymous = create_client()
    worker = create_client()
    login_user(worker, "batch-uploader", "uploader-pass")

    for endpoint in ("/接口/回收站/批量恢复", "/接口/回收站/批量彻底删除"):
        assert anonymous.post(endpoint, json={"ids": ids}).status_code == 401
        assert worker.post(endpoint, json={"ids": ids}).status_code == 403

    # 空数组与超过上限的数组都由 schema 拦下来，不会打到业务逻辑。
    assert client.post("/接口/回收站/批量恢复", json={"ids": []}).status_code == 422
    too_many = list(range(1, 300))
    assert (
        client.post("/接口/回收站/批量彻底删除", json={"ids": too_many}).status_code == 422
    )


def test_trash_batch_routes_are_not_shadowed_by_file_id(tmp_path, monkeypatch):
    """回归：/api/trash/batch/restore 与 /api/trash/{file_id}/restore 段数相同。

    先注册的参数路由会把「batch」当成编号解析，直接 422。这里锁住注册顺序。
    """

    client, _, _, ids = trash_client(tmp_path, monkeypatch)

    response = client.post("/api/trash/batch/restore", json={"ids": ids[:1]})
    assert response.status_code == 200, response.text
    assert response.json()["succeeded"] == 1
    # 参数路由本身仍然可用。
    assert client.post(f"/api/trash/{ids[1]}/restore").status_code == 200


def test_trash_retention_purges_expired_files(tmp_path, monkeypatch):
    import sqlite3

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import configure_connection, init_db, purge_deleted_files

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "过期回收站"}).json()
    fresh = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "刚删除的"},
        files={"file": ("fresh.txt", b"fresh", "text/plain")},
    ).json()
    stale = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "很久前删除的"},
        files={"file": ("stale.txt", b"stale", "text/plain")},
    ).json()
    assert client.delete(f"/接口/资料/{fresh['id']}").status_code == 204
    assert client.delete(f"/接口/资料/{stale['id']}").status_code == 204

    # purge_deleted_files 内部会调用 stage_stored_files，后者按列名取 filename，
    # 所以这个手开的连接也必须先按应用的方式配置好 row_factory。
    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "UPDATE files SET deleted_at = datetime('now', '-40 days') WHERE id = ?",
        (stale["id"],),
    )
    connection.commit()

    # 保留 30 天：只清掉 40 天前那条，刚删的那条要留着。
    assert purge_deleted_files(connection, 30) == 1
    remaining = [row[0] for row in connection.execute("SELECT id FROM files")]
    assert remaining == [fresh["id"]]
    connection.close()
    assert len(list(uploads.iterdir())) == 1

    # 保留期设为 0 表示不清空回收站。
    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    assert purge_deleted_files(connection, 0) == 0
    connection.close()


def test_deleted_file_can_be_uploaded_again(tmp_path, monkeypatch):
    """同一课程删掉一份资料后，同样的内容必须能重新上传。

    内容去重唯一索引原本是 (course_id, sha256)，软删除后已删行仍占着约束，
    会把重新上传挡成 409；索引条件加上 deleted_at IS NULL 才能放行。
    """

    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "重复上传课程"}).json()
    payload = {"title": "同一份内容", "file": ("same.txt", b"same-content", "text/plain")}

    first = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": payload["title"]},
        files={"file": payload["file"]},
    )
    assert first.status_code == 201
    # 未删除时同内容仍然被拒。
    duplicate = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": payload["title"]},
        files={"file": payload["file"]},
    )
    assert duplicate.status_code == 409

    assert client.delete(f"/接口/资料/{first.json()['id']}").status_code == 204
    again = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": payload["title"]},
        files={"file": payload["file"]},
    )
    assert again.status_code == 201, again.text


def test_restore_fails_when_same_content_exists(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "冲突课程"}).json()
    first = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "第一份"},
        files={"file": ("first.txt", b"identical-bytes", "text/plain")},
    ).json()
    assert client.delete(f"/接口/资料/{first['id']}").status_code == 204
    # 删掉之后同内容可以重新传进来。
    second = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "第二份"},
        files={"file": ("second.txt", b"identical-bytes", "text/plain")},
    )
    assert second.status_code == 201
    # 此时再恢复第一份会撞上唯一索引，应给出 409 而不是 500。
    conflict = client.post(f"/接口/回收站/{first['id']}/恢复")
    assert conflict.status_code == 409
    assert "相同" in conflict.json()["error"]["message"]
    # 恢复失败后记录仍留在回收站，没有被破坏。
    assert client.get("/接口/回收站").json()["total"] == 1


def test_trash_is_hidden_from_listings_and_search(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "隐藏检查课程"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "独一无二关键词资料"},
        files={"file": ("unique-keyword.txt", b"unique-keyword", "text/plain")},
    ).json()

    def hits() -> int:
        return client.get(
            "/接口/搜索", params={"关键词": "独一无二关键词"}
        ).json()["total"]

    assert hits() == 1
    assert client.get("/接口/课程").json()["total"] == 1
    detail = client.get(f"/接口/课程/{course['id']}").json()
    assert detail["file_count"] == 1

    assert client.delete(f"/接口/资料/{uploaded['id']}").status_code == 204

    # 全文索引是外部内容表，软删除不会触发它的删除触发器，必须靠查询里的
    # deleted_at 过滤，否则已删资料仍会被搜出来。
    assert hits() == 0
    assert client.get(f"/接口/课程/{course['id']}").json()["file_count"] == 0
    # 下载与预览也要挡住。
    assert client.get(f"/接口/资料/{uploaded['id']}/下载").status_code == 404
    assert client.get(f"/接口/资料/{uploaded['id']}/预览").status_code == 404
    # 已删除的资料不能再编辑或审核。
    edit = client.patch(f"/接口/资料/{uploaded['id']}", json={"title": "改名"})
    assert edit.status_code == 404
    review = client.patch(
        f"/接口/资料/{uploaded['id']}/审核", json={"status": "rejected"}
    )
    assert review.status_code == 404


def test_trash_endpoints_require_admin(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    created = client.post(
        "/接口/用户",
        json={"username": "trash-viewer", "password": "viewer-pass", "role": "uploader"},
    )
    assert created.status_code == 201

    anonymous = create_client()
    assert anonymous.get("/接口/回收站").status_code == 401

    worker = create_client()
    login_user(worker, "trash-viewer", "viewer-pass")
    assert worker.get("/接口/回收站").status_code == 403
    assert worker.post("/接口/回收站/1/恢复").status_code == 403
    assert worker.delete("/接口/回收站/1").status_code == 403


def _upload_named(client, course_id: int, title: str, filename: str, content: bytes) -> dict:
    response = client.post(
        f"/接口/课程/{course_id}/资料",
        data={"title": title},
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


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


def test_favicon_routes_are_available():
    client = create_client()

    icon = client.get("/资源/图标.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    # 图标很小、每会话只取一次，不参与版本号，走「每次校验」即可。
    assert icon.headers["Cache-Control"] == "no-cache"

    # 浏览器会无条件探测 /favicon.ico，回 204 比 404 干净。
    assert client.get("/favicon.ico").status_code == 204


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


def test_health_probe_cleanup_removes_only_stale_probes(tmp_path, monkeypatch):
    import os
    import time as time_module

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import cleanup_health_probes

    stale = uploads / ".health-stale"
    fresh = uploads / ".health-fresh"
    real_upload = uploads / "3f2a9c1b4d5e6f70"
    for path in (stale, fresh, real_upload):
        path.write_bytes(b"")

    two_hours_ago = time_module.time() - 2 * 60 * 60
    os.utime(stale, (two_hours_ago, two_hours_ago))

    assert cleanup_health_probes() == 1
    assert not stale.exists()
    # 一小时内的探针可能正属于正在进行的健康检查，不能删。
    assert fresh.exists()
    # 真正的上传文件用的是随机名、不以点开头，永远不碰。
    assert real_upload.exists()


def test_health_check_survives_probe_cleanup_failure(tmp_path, monkeypatch):
    from pathlib import Path

    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()

    # Windows 上杀毒软件会短暂锁住刚创建的文件，让删除抛 PermissionError。
    # 那只是清理失败，不该把实例判成不健康。
    def broken_unlink(self, *args, **kwargs):
        raise PermissionError(13, "文件被占用")

    monkeypatch.setattr(Path, "unlink", broken_unlink)

    body = client.get("/接口/健康").json()
    assert body["checks"]["uploads"]["status"] == "ok"


def _make_user(client, username: str, role: str = "uploader") -> dict:
    response = client.post(
        "/接口/用户",
        json={"username": username, "password": f"{username}-pass", "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _user_map(client) -> dict:
    page = client.get("/接口/用户", params={"page_size": 100}).json()
    return {item["id"]: item for item in page["items"]}


def test_batch_update_users_enables_and_disables(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    first = _make_user(client, "batch-one")
    second = _make_user(client, "batch-two")

    disabled = client.post(
        "/接口/用户/批量修改",
        json={"ids": [first["id"], second["id"]], "action": "disable"},
    )
    assert disabled.status_code == 200
    assert (disabled.json()["succeeded"], disabled.json()["failed"]) == (2, 0)

    users = _user_map(client)
    assert users[first["id"]]["is_active"] is False
    assert users[second["id"]]["is_active"] is False

    enabled = client.post(
        "/接口/用户/批量修改",
        json={"ids": [first["id"]], "action": "enable"},
    )
    assert enabled.json()["succeeded"] == 1
    users = _user_map(client)
    assert users[first["id"]]["is_active"] is True
    assert users[second["id"]]["is_active"] is False


def test_batch_update_users_reports_each_failure(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    target = _make_user(client, "batch-partial")
    me = client.get("/接口/当前用户").json()

    # 一个正常、一个不存在、一个是我自己（不能停用自己）。
    response = client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"], 999999, me["id"]], "action": "disable"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (1, 2)

    results = {item["id"]: item for item in body["items"]}
    assert results[target["id"]]["ok"] is True
    assert results[999999]["ok"] is False
    assert results[999999]["message"] == "用户不存在"
    # 批量接口复用单条逻辑，所以「不能停用自己」这条规则照样拦得住。
    assert results[me["id"]]["ok"] is False
    assert results[me["id"]]["message"] == "不能停用当前登录的账户"
    assert _user_map(client)[me["id"]]["is_active"] is True


def test_batch_update_users_changes_role(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    target = _make_user(client, "batch-role")

    response = client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"]], "action": "role", "role": "viewer"},
    )
    assert response.json()["succeeded"] == 1
    assert _user_map(client)[target["id"]]["role"] == "viewer"

    # 改角色却不给目标角色属于请求错误，不能静默成功。
    assert client.post(
        "/接口/用户/批量修改",
        json={"ids": [target["id"]], "action": "role"},
    ).status_code == 422
    # 空编号列表同理。
    assert client.post(
        "/接口/用户/批量修改",
        json={"ids": [], "action": "enable"},
    ).status_code == 422


def test_batch_review_files_approves_and_rejects(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "批量审核"}).json()
    # 管理员上传默认是已通过，这里靠批量审核把它改成别的状态。
    first = _upload_named(client, course["id"], "甲", "a.txt", b"a")
    second = _upload_named(client, course["id"], "乙", "b.txt", b"b")
    third = _upload_named(client, course["id"], "丙", "c.txt", b"c")

    rejected = client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"]], "status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["succeeded"] == 2

    files = client.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    statuses = {item["id"]: item["status"] for item in files}
    assert statuses[first["id"]] == "rejected"
    assert statuses[second["id"]] == "rejected"
    assert statuses[third["id"]] == "approved"

    approved = client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"], 999999], "status": "approved"},
    )
    body = approved.json()
    assert (body["succeeded"], body["failed"]) == (2, 1)
    results = {item["id"]: item for item in body["items"]}
    assert results[first["id"]]["message"] == "已通过"
    assert results[999999]["message"] == "资料不存在"

    files = client.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    assert {item["id"]: item["status"] for item in files}[first["id"]] == "approved"


def test_batch_review_records_one_audit_entry_per_file(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "批量审核审计"}).json()
    first = _upload_named(client, course["id"], "甲", "a.txt", b"a")
    second = _upload_named(client, course["id"], "乙", "b.txt", b"b")

    assert client.post(
        "/接口/资料/批量审核",
        json={"ids": [first["id"], second["id"]], "status": "rejected"},
    ).status_code == 200

    records = client.get("/接口/审计", params={"动作": "rejected"}).json()
    assert records["total"] >= 2
    # 批量操作也是逐条记审计，而不是只记一条「批量审核」。
    assert {item["entity_id"] for item in records["items"]} >= {first["id"], second["id"]}


def test_batch_endpoints_require_admin(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    _make_user(client, "batch-plain", role="viewer")

    anonymous = create_client()
    assert anonymous.post(
        "/接口/用户/批量修改", json={"ids": [1], "action": "disable"}
    ).status_code == 401
    assert anonymous.post(
        "/接口/资料/批量审核", json={"ids": [1], "status": "approved"}
    ).status_code == 401

    viewer = create_client()
    login_user(viewer, "batch-plain", "batch-plain-pass")
    assert viewer.post(
        "/接口/用户/批量修改", json={"ids": [1], "action": "disable"}
    ).status_code == 403
    assert viewer.post(
        "/接口/资料/批量审核", json={"ids": [1], "status": "approved"}
    ).status_code == 403


def test_error_pages_are_html_for_browsers_and_json_for_api():
    client = create_client()
    browser_headers = {"Accept": "text/html,application/xhtml+xml"}

    # 浏览器直接访问不存在的地址：拿到一张看得懂的中文页面。
    page = client.get("/不存在的路径", headers=browser_headers)
    assert page.status_code == 404
    assert page.headers["content-type"].startswith("text/html")
    assert "没有找到这个页面" in page.text
    assert page.headers["Cache-Control"] == "no-cache"
    # 页面里引用的静态资源地址同样带版本号。
    assert 'href="/资源/样式.css?v=' in page.text
    assert "{{asset_version}}" not in page.text

    # 同一个地址，接口调用方（不接受 HTML）仍然拿 JSON。
    api = client.get("/不存在的路径", headers={"Accept": "application/json"})
    assert api.status_code == 404
    assert api.headers["content-type"].startswith("application/json")
    assert api.json()["error"]["code"] == "not_found"

    # /接口 前缀下的 404 一律回 JSON，哪怕请求头明确要 HTML。
    interface = client.get("/接口/课程/999999", headers=browser_headers)
    assert interface.status_code == 404
    assert interface.headers["content-type"].startswith("application/json")
    assert interface.json()["error"]["code"] == "not_found"


def test_error_page_escapes_detail():
    from app.main import render_error_page

    page = render_error_page(418, "<script>alert(1)</script>")
    body = page.body.decode("utf-8")
    # detail 可能来自用户可控的内容，拼进 HTML 前必须转义。
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def _iter_api_routes(application):
    """展开 FastAPI 延迟加载的子路由，拿到真正的 APIRoute 列表。

    FastAPI 0.141 起 include_router 放进 app.routes 的是一个 _IncludedRouter 占位符，
    真正的路由挂在它的 original_router 上，直接遍历 app.routes 会什么都看不到。
    """
    for route in application.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original)
        elif getattr(route, "methods", None) and getattr(route, "path", "").startswith(
            "/api"
        ):
            yield route


def _route_shape(path: str) -> str:
    """把 /api/files/{file_id} 与 /api/files/${...} 归一成同一形状再比对。"""
    return re.sub(r"\$?\{[^}]*\}", "{}", path)


def _frontend_api_calls(source: str) -> list[tuple[str, str]]:
    """从 app.js 里抽出所有指向 /api 的 fetch 调用，返回 (方法, 路径) 列表。"""
    pattern = re.compile(r"fetch\(\s*(?:\"([^\"]*)\"|`([^`]*)`)")
    matches = list(pattern.finditer(source))
    calls: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        raw = match.group(1) or match.group(2) or ""
        path = raw.split("?")[0]
        if not path.startswith("/api"):
            continue
        # method 只在这条 fetch 到下一条 fetch 之间找，否则会把后面的调用算到前面。
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        method_match = re.search(r"method:\s*\"([A-Z]+)\"", source[match.end() : end])
        method = method_match.group(1) if method_match else "GET"
        calls.append((method, path))
    return calls


def test_frontend_fetch_calls_match_registered_routes():
    """app.js 里每个 fetch 的「路径 + 方法」都必须在后端真实存在。

    回归背景：批量审核在后端因为路由注册顺序从 PATCH 改成了 POST，
    但 app.js 忘了跟着改，线上点「批量通过 / 批量拒绝」会拿到 405。
    pytest 打的是接口，前端 JS 平时不在测试范围内，所以这条专盯两者的接缝。
    """
    routes: dict[str, set[str]] = {}
    for route in _iter_api_routes(app):
        routes.setdefault(_route_shape(route.path), set()).update(
            route.methods - {"HEAD", "OPTIONS"}
        )
    # 后端路由表本身要能解析出来，否则下面的比对会「因为空所以全过」。
    assert routes.get("/api/courses") == {"GET", "POST"}, sorted(routes)

    source = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    calls = _frontend_api_calls(source)
    assert calls, "没从 app.js 解析出任何 /api 调用，解析规则可能已过期"
    assert ("POST", "/api/files/batch/review") in calls

    problems = []
    for method, path in calls:
        allowed = routes.get(_route_shape(path))
        if allowed is None:
            problems.append(f"{method} {path} —— 后端没有这个路径")
        elif method not in allowed:
            problems.append(
                f"{method} {path} —— 后端只允许 {'/'.join(sorted(allowed))}"
            )
    assert not problems, "前端调用了后端不接受的接口：\n" + "\n".join(sorted(set(problems)))


def _make_stale_probe(uploads: Path) -> Path:
    """在 uploads 里造一个「过期」的健康检查探针，供启动清理逻辑消费。"""
    uploads.mkdir(parents=True, exist_ok=True)
    probe = uploads / ".health-stale-probe"
    probe.write_bytes(b"")
    stale = time.time() - 7200
    os.utime(probe, (stale, stale))
    return probe


def test_importing_app_does_not_touch_uploads(tmp_path):
    """导入 app.main 只是加载代码，不该删 uploads 里的任何文件。

    回归背景：启动维护一度写在模块导入时执行，于是 pytest 收集测试（收集阶段就会
    import app.main）顺手把 uploads 里的残留探针删了；任何文档工具、linter 只要
    import 一次也会触发一遍破坏性维护。现在维护挪进了 lifespan。
    """
    uploads = tmp_path / "uploads"
    probe = _make_stale_probe(uploads)

    environment = dict(os.environ)
    environment["COURSEBOX_DB"] = str(tmp_path / "import.db")
    environment["COURSEBOX_UPLOAD_DIR"] = str(uploads)
    completed = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=Path(__file__).resolve().parent.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert probe.exists(), "导入 app.main 不应该删除 uploads 里的文件"


def test_startup_maintenance_runs_when_app_starts(tmp_path, monkeypatch):
    """真正启动应用（进入 lifespan）时才会执行启动维护。"""
    uploads = tmp_path / "uploads"
    probe = _make_stale_probe(uploads)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "startup.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))
    reset_initialized_databases()

    with TestClient(app):
        pass

    assert not probe.exists(), "应用启动（lifespan）应该清掉过期的健康检查探针"


