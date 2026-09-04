from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/接口/健康")

    assert response.status_code == 200
    assert response.json()["app"] == "CourseBox"
    assert response.json()["应用"] == "课盒子"


def test_pages_are_available():
    homepage = client.get("/")
    course_page = client.get("/课程")
    chinese_script = client.get("/资源/脚本.js")
    chinese_style = client.get("/资源/样式.css")

    assert homepage.status_code == 200
    assert "全部课程" in homepage.text
    assert 'id="search-form"' in homepage.text
    assert course_page.status_code == 200
    assert 'id="upload-form"' in course_page.text
    assert chinese_script.status_code == 200
    assert chinese_style.status_code == 200


def test_create_and_list_courses(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    create_response = client.post(
        "/接口/课程",
        json={"name": "数据结构", "college": "计算机学院", "semester": "2026 春"},
    )

    assert create_response.status_code == 201
    course = create_response.json()
    assert course["name"] == "数据结构"

    list_response = client.get("/接口/课程")

    assert list_response.status_code == 200
    assert any(item["id"] == course["id"] for item in list_response.json())


def test_course_name_is_required():
    response = client.post("/接口/课程", json={"name": ""})

    assert response.status_code == 422


def test_upload_and_list_files(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()
    response = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "课件"},
        files={"file": ("lesson.txt", b"hello CourseBox", "text/plain")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["original_name"] == "lesson.txt"
    assert uploaded["size"] == len(b"hello CourseBox")

    files_response = client.get(f"/接口/课程/{course['id']}/资料")

    assert files_response.status_code == 200
    assert files_response.json()[0]["title"] == "课件"


def test_upload_to_missing_course_returns_404():
    response = client.post(
        "/接口/课程/999999/资料",
        data={"title": "课件"},
        files={"file": ("lesson.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


def test_download_and_search_file(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    course = client.post("/接口/课程", json={"name": "数据结构"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "树与图讲义"},
        files={"file": ("数据结构.pdf", b"pdf-content", "application/pdf")},
    )
    file_id = upload.json()["id"]

    download = client.get(f"/接口/资料/{file_id}/下载")
    search = client.get("/接口/搜索", params={"关键词": "数据结构"})

    assert download.status_code == 200
    assert download.content == b"pdf-content"
    assert "数据结构.pdf" in unquote(download.headers["content-disposition"])
    assert search.status_code == 200
    assert search.json()[0]["course"]["name"] == "数据结构"


def test_search_empty_query_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    response = client.get("/接口/搜索", params={"关键词": "   "})

    assert response.status_code == 200
    assert response.json() == []


def test_chinese_routes_are_the_only_public_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    course = client.post("/接口/课程", json={"name": "中文接口测试"}).json()
    upload = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "测试资料"},
        files={"file": ("测试.txt", b"chinese-route", "text/plain")},
    )

    assert client.get("/接口/课程").status_code == 200
    assert upload.status_code == 201
    file_id = upload.json()["id"]
    assert client.get("/接口/课程/" + str(course["id"]) + "/资料").status_code == 200
    download = client.get(f"/接口/资料/{file_id}/下载")
    search = client.get("/接口/搜索", params={"关键词": "中文接口测试"})
    assert download.status_code == 200
    assert download.content == b"chinese-route"
    assert search.status_code == 200
    assert search.json()[0]["course"]["name"] == "中文接口测试"

    assert client.get("/api/courses").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/资源/app.js").status_code == 404
    assert client.get("/course.html").status_code == 404

    documented_paths = client.get("/接口定义").json()["paths"]
    assert all(not path.startswith("/api/") for path in documented_paths)
    assert all("files" not in path and "search" not in path for path in documented_paths)
    assert all("course_id" not in path and "file_id" not in path for path in documented_paths)
    assert all("Course" not in str(item) for item in documented_paths.values())
