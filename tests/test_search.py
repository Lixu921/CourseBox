from conftest import create_client, login_admin


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
