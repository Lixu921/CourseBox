from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["app"] == "CourseBox"


def test_pages_are_available():
    homepage = client.get("/")
    course_page = client.get("/course.html")

    assert homepage.status_code == 200
    assert "全部课程" in homepage.text
    assert 'id="search-form"' in homepage.text
    assert course_page.status_code == 200
    assert 'id="upload-form"' in course_page.text


def test_create_and_list_courses(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    create_response = client.post(
        "/api/courses",
        json={"name": "数据结构", "college": "计算机学院", "semester": "2026 春"},
    )

    assert create_response.status_code == 201
    course = create_response.json()
    assert course["name"] == "数据结构"

    list_response = client.get("/api/courses")

    assert list_response.status_code == 200
    assert any(item["id"] == course["id"] for item in list_response.json())


def test_course_name_is_required():
    response = client.post("/api/courses", json={"name": ""})

    assert response.status_code == 422


def test_upload_and_list_files(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    course = client.post("/api/courses", json={"name": "数据结构"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "课件"},
        files={"file": ("lesson.txt", b"hello CourseBox", "text/plain")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["original_name"] == "lesson.txt"
    assert uploaded["size"] == len(b"hello CourseBox")

    files_response = client.get(f"/api/courses/{course['id']}/files")

    assert files_response.status_code == 200
    assert files_response.json()[0]["title"] == "课件"


def test_upload_to_missing_course_returns_404():
    response = client.post(
        "/api/courses/999999/files",
        data={"title": "课件"},
        files={"file": ("lesson.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


def test_download_and_search_file(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    course = client.post("/api/courses", json={"name": "数据结构"}).json()
    upload = client.post(
        f"/api/courses/{course['id']}/files",
        data={"title": "树与图讲义"},
        files={"file": ("数据结构.pdf", b"pdf-content", "application/pdf")},
    )
    file_id = upload.json()["id"]

    download = client.get(f"/api/files/{file_id}/download")
    search = client.get("/api/search", params={"q": "数据结构"})

    assert download.status_code == 200
    assert download.content == b"pdf-content"
    assert "数据结构.pdf" in unquote(download.headers["content-disposition"])
    assert search.status_code == 200
    assert search.json()[0]["course"]["name"] == "数据结构"


def test_search_empty_query_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    response = client.get("/api/search", params={"q": "   "})

    assert response.status_code == 200
    assert response.json() == []
