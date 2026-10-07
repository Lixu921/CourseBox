import codecs
import csv
import io

from conftest import create_client, login_admin, login_user


def _csv_rows(response) -> list[list[str]]:
    """把 CSV 响应解析回二维表，顺便把「BOM + CRLF」这两条约定一起钉住。"""

    raw = response.content
    assert raw.startswith(codecs.BOM_UTF8), "导出必须带 UTF-8 BOM，否则 Excel 打开是乱码"
    text = raw.decode("utf-8-sig")
    assert "\r\n" in text, "必须用 CRLF 换行，老版本 Excel 对 LF 兼容不好"
    return list(csv.reader(io.StringIO(text)))


def test_export_course_files_csv(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post(
        "/接口/课程",
        json={"name": "数据结构", "college": "计算机学院", "semester": "2026 春"},
    ).json()
    for index, (title, name) in enumerate((("绪论", "intro.pdf"), ("习题一", "hw1.pdf"))):
        assert client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": title},
            # 内容必须各不相同，否则会撞上「同课程 + 同 sha256」的去重索引。
            files={"file": (name, f"content-{index}".encode(), "application/pdf")},
        ).status_code == 201

    response = client.get(f"/接口/课程/{course['id']}/资料导出")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "charset=utf-8" in response.headers["content-type"].lower()
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    # 中文文件名要走 RFC 5987 的 filename*，否则浏览器会存成乱码。
    assert "filename*=UTF-8''" in disposition

    rows = _csv_rows(response)
    assert rows[0][:4] == ["资料编号", "标题", "文件名", "大小(字节)"]
    assert len(rows) == 3  # 表头 + 两份资料
    titles = {row[1] for row in rows[1:]}
    assert titles == {"绪论", "习题一"}
    assert {row[5] for row in rows[1:]} == {"已通过"}
    assert {row[8] for row in rows[1:]} == {"数据结构"}

    # 导出动作本身要留痕，否则「谁把清单带走了」查不到。
    records = client.get("/接口/审计", params={"动作": "export"}).json()["items"]
    assert any("导出课程资料清单" in (item["detail"] or "") for item in records), records


def test_export_course_files_respects_visibility(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "可见性课程"}).json()
    assert client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "已通过的资料"},
        files={"file": ("ok.pdf", b"a" * 32, "application/pdf")},
    ).status_code == 201
    assert client.post(
        "/接口/用户",
        json={"username": "exporter", "password": "exporter-pass", "role": "uploader"},
    ).status_code == 201

    worker = create_client()
    login_user(worker, "exporter", "exporter-pass")
    assert worker.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "待审资料"},
        files={"file": ("pending.pdf", b"b" * 32, "application/pdf")},
    ).status_code == 201
    # 访客只能拿到已通过的那一份；能翻页看到什么，导出就该只给什么。
    visitor_rows = _csv_rows(create_client().get(f"/接口/课程/{course['id']}/资料导出"))
    assert {row[1] for row in visitor_rows[1:]} == {"已通过的资料"}
    assert {row[5] for row in visitor_rows[1:]} == {"已通过"}

    # 上传者额外能看到自己那份待审资料。
    worker_rows = _csv_rows(worker.get(f"/接口/课程/{course['id']}/资料导出"))
    assert {row[1] for row in worker_rows[1:]} == {"已通过的资料", "待审资料"}

    # 管理员全都能看到。
    admin_rows = _csv_rows(client.get(f"/接口/课程/{course['id']}/资料导出"))
    assert len(admin_rows) == 3

    assert client.get("/接口/课程/999999/资料导出").status_code == 404


def test_export_csv_neutralizes_formula_injection(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "公式课程"}).json()
    # 标题以 = 开头，直接导出会变成 Excel 公式。
    assert client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "=1+1"},
        files={"file": ("f.txt", b"x", "text/plain")},
    ).status_code == 201
    # 带逗号和引号的标题交给 csv 模块转义。
    assert client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": '含,逗号"与引号'},
        files={"file": ("g.txt", b"y", "text/plain")},
    ).status_code == 201

    rows = _csv_rows(client.get(f"/接口/课程/{course['id']}/资料导出"))
    titles = {row[1] for row in rows[1:]}
    assert "'=1+1" in titles, titles
    assert '含,逗号"与引号' in titles, titles


def test_export_refuses_to_truncate_over_limit(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("COURSEBOX_EXPORT_MAX_ROWS", "1")

    from app.db import init_db

    init_db()
    login_admin(client)
    course = client.post("/接口/课程", json={"name": "超限课程"}).json()
    for index in range(2):
        assert client.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": f"资料 {index}"},
            files={"file": (f"f{index}.txt", f"x{index}".encode(), "text/plain")},
        ).status_code == 201

    # 超限必须报错，不能悄悄只导出一半——被截断的清单看起来是完整的。
    response = client.get(f"/接口/课程/{course['id']}/资料导出")
    assert response.status_code == 413
    assert "1" in response.json()["detail"]

    # 删掉一份后就正好等于上限，这时可以正常导出。
    listing = client.get(f"/接口/课程/{course['id']}/资料").json()
    assert client.delete(f"/接口/资料/{listing['items'][0]['id']}").status_code == 204
    ok = client.get(f"/接口/课程/{course['id']}/资料导出")
    assert ok.status_code == 200
    assert len(_csv_rows(ok)) == 2


def test_export_audit_csv(tmp_path, monkeypatch):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()

    anonymous = create_client()
    assert anonymous.get("/接口/审计导出").status_code == 401

    login_admin(client)
    client.post("/接口/课程", json={"name": "审计课程"})

    response = client.get("/接口/审计导出")
    assert response.status_code == 200, response.text
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    rows = _csv_rows(response)
    assert rows[0] == ["编号", "时间", "操作人", "动作", "对象", "对象编号", "详情"]
    actions = {row[3] for row in rows[1:]}
    # 动作导出成中文，方便直接交给别人看。
    assert "登录" in actions
    assert "新建" in actions
    # 这一次导出自己的记录当然还不在结果里（记录是在取完数据之后才写的）……
    assert "导出" not in actions
    # ……所以再导一次，上一次的导出记录就该出现了。
    again = {row[3] for row in _csv_rows(client.get("/接口/审计导出"))[1:]}
    assert "导出" in again

    # 筛选条件与列表接口一致。
    only_login = _csv_rows(client.get("/接口/审计导出", params={"动作": "login"}))
    assert {row[3] for row in only_login[1:]} == {"登录"}
    assert (
        client.get(
            "/接口/审计导出", params={"起始时间": "2026-01-02", "结束时间": "2026-01-01"}
        ).status_code
        == 422
    )
    assert client.get("/接口/审计导出", params={"动作": "bogus"}).status_code == 422

    # 非管理员不能导出。
    assert client.post(
        "/接口/用户",
        json={"username": "audit-viewer", "password": "viewer-pass", "role": "viewer"},
    ).status_code == 201
    viewer = create_client()
    login_user(viewer, "audit-viewer", "viewer-pass")
    assert viewer.get("/接口/审计导出").status_code == 403


def test_csv_export_helpers_units():
    from app.csv_export import escape_cell, render_csv

    assert escape_cell(None) == ""
    assert escape_cell(True) == "是"
    assert escape_cell(False) == "否"
    assert escape_cell(12) == "12"
    for dangerous in ("=SUM(A1)", "+1", "-1", "@x", "\tx", "\rx"):
        assert escape_cell(dangerous) == "'" + dangerous, dangerous
    assert escape_cell("普通文本") == "普通文本"

    payload = render_csv(("a", "b"), [(1, None), ("含,逗号", '有"引号')])
    assert payload.startswith(codecs.BOM_UTF8)
    text = payload.decode("utf-8-sig")
    assert text == 'a,b\r\n1,\r\n"含,逗号","有""引号"\r\n'
