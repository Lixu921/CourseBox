from conftest import create_client, login_admin, login_user


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
