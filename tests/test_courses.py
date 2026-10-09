from conftest import create_client, login_admin
from fastapi.testclient import TestClient

from app.main import app


def test_create_and_list_courses(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import init_db

    init_db()
    login_admin(client)
    create_response = client.post(
        "/\u63a5\u53e3/\u8bfe\u7a0b",
        json={"name": "Data Structures", "college": "Computer Science"},
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
        json={"name": "  数据结构  ", "college": "  计算机学院  "},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "数据结构"
    assert created.json()["college"] == "计算机学院"

    blank_optional = client.patch(
        f"/接口/课程/{created.json()['id']}",
        json={"college": "   "},
    )
    assert blank_optional.status_code == 200
    assert blank_optional.json()["college"] is None
    assert client.patch(
        f"/接口/课程/{created.json()['id']}", json={"name": None}
    ).status_code == 422
    assert client.post("/接口/课程", json={"name": "x" * 201}).status_code == 422
    assert client.post(
        "/接口/课程", json={"name": "x", "college": "y" * 121}
    ).status_code == 422
    assert client.post("/接口/课程", json={"name": 123}).status_code == 422


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
        "items": [
            {
                "id": 1,
                "name": "课程一",
                "college": None,
                "version": 1,
                "tags": [],
            }
        ],
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
        json={"name": "新课程"},
    )
    assert updated_course.status_code == 200
    assert updated_course.json()["name"] == "新课程"
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
        json={"name": "数据结构", "college": "计算机学院"},
    )
    client.post(
        "/接口/课程",
        json={"name": "高等数学", "college": "数学学院"},
    )
    client.post("/接口/课程", json={"name": "线性代数"})

    assert client.get("/接口/课程").json()["total"] == 3

    # 关键词分别命中课程名、学院。
    assert client.get("/接口/课程", params={"关键词": "高等"}).json()["total"] == 1
    assert client.get("/接口/课程", params={"关键词": "计算机"}).json()["total"] == 1
    assert client.get("/接口/课程", params={"关键词": "学院"}).json()["total"] == 2
    assert client.get("/接口/课程", params={"关键词": "不存在"}).json()["total"] == 0

    # 通配符要被转义，不能把 % 当成"匹配全部"。
    assert client.get("/接口/课程", params={"关键词": "%"}).json()["total"] == 0
    assert client.get("/接口/课程", params={"关键词": "_"}).json()["total"] == 0

    # 关键词与分页同时生效。
    paged = client.get(
        "/接口/课程", params={"关键词": "学院", "page": 1, "page_size": 1}
    ).json()
    assert len(paged["items"]) == 1
    assert paged["total"] == 2
    assert paged["total_pages"] == 2


def test_course_edit_optimistic_lock(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "并发课程"}).json()
    assert course["version"] == 1

    ok = client.patch(
        f"/接口/课程/{course['id']}", json={"name": "第一次改名", "version": 1}
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == 2

    # 拿着过期的版本号再改 → 409，不会覆盖别人的修改。
    conflict = client.patch(
        f"/接口/课程/{course['id']}", json={"name": "回退覆盖", "version": 1}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"
    assert client.get(f"/接口/课程/{course['id']}").json()["name"] == "第一次改名"

    # 不传版本号退化为后写覆盖，保持旧客户端兼容。
    assert client.patch(
        f"/接口/课程/{course['id']}", json={"name": "无版本覆盖"}
    ).status_code == 200
    assert client.get(f"/接口/课程/{course['id']}").json()["version"] == 3


def test_course_tags(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)

    created = client.post(
        "/接口/课程",
        json={"name": "高数", "tags": ["必修", "  大二  ", "必修"]},
    ).json()
    # 去重、去空白。
    assert created["tags"] == ["必修", "大二"]
    assert client.get(f"/接口/课程/{created['id']}").json()["tags"] == ["必修", "大二"]

    client.post("/接口/课程", json={"name": "线代", "tags": ["选修"]})

    # 标签精确筛选：整个标签相等，不做子串。
    filtered = client.get("/接口/课程", params={"标签": "必修"}).json()
    assert [item["id"] for item in filtered["items"]] == [created["id"]]
    assert client.get("/接口/课程", params={"标签": "必"}).json()["total"] == 0

    # 关键词也能命中标签。
    assert client.get("/接口/课程", params={"关键词": "大二"}).json()["total"] == 1

    updated = client.patch(
        f"/接口/课程/{created['id']}",
        json={"tags": ["选修"], "version": created["version"]},
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["选修"]

    cleared = client.patch(f"/接口/课程/{created['id']}", json={"tags": []})
    assert cleared.json()["tags"] == []


def test_course_name_cannot_repeat(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)

    assert client.post("/接口/课程", json={"name": "高等数学"}).status_code == 201
    duplicate = client.post("/接口/课程", json={"name": "高等数学"})
    assert duplicate.status_code == 409
    assert "已存在" in duplicate.json()["error"]["message"]

    other = client.post("/接口/课程", json={"name": "线性代数"}).json()
    # 改名撞上已有课程也要被拒。
    clash = client.patch(f"/接口/课程/{other['id']}", json={"name": "高等数学"})
    assert clash.status_code == 409
