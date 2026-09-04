import os

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["app"] == "CourseBox"


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
