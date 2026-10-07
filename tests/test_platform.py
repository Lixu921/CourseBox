import logging

from conftest import create_client, login_admin
from fastapi.testclient import TestClient

from app.db import reset_initialized_databases
from app.main import app


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


def test_favicon_routes_are_available():
    client = create_client()

    icon = client.get("/资源/图标.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    # 图标很小、每会话只取一次，不参与版本号，走「每次校验」即可。
    assert icon.headers["Cache-Control"] == "no-cache"

    # 浏览器会无条件探测 /favicon.ico，回 204 比 404 干净。
    assert client.get("/favicon.ico").status_code == 204


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
