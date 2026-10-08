"""并发一致性回归。

这些用例用两个连接同时发起「本应互斥」的写操作，验证服务端真正做到了原子：
- 课程 / 资料的乐观锁；
- 「至少保留一个启用管理员」；
- 上传配额。
它们单请求测不出来，必须并发。
"""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from conftest import create_client, login_admin


def _setup(tmp_path, monkeypatch, **env):
    client = create_client()
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    from app.db import init_db

    init_db()
    login_admin(client)
    return client


def _run_together(call, *args_per_call):
    barrier = threading.Barrier(len(args_per_call))

    def wrapped(*args):
        barrier.wait()
        return call(*args)

    with ThreadPoolExecutor(max_workers=len(args_per_call)) as pool:
        futures = [pool.submit(wrapped, *args) for args in args_per_call]
        return [future.result() for future in futures]


def test_concurrent_course_edits_are_serialized(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    course = client.post("/接口/课程", json={"name": "并发课"}).json()
    assert course["version"] == 1

    first = create_client()
    login_admin(first)
    second = create_client()
    login_admin(second)

    def edit(session, name):
        return session.patch(
            f"/接口/课程/{course['id']}", json={"name": name, "version": 1}
        )

    responses = _run_together(edit, (first, "甲"), (second, "乙"))
    assert sorted(response.status_code for response in responses) == [200, 409]

    detail = client.get(f"/接口/课程/{course['id']}").json()
    assert detail["version"] == 2
    assert detail["name"] in {"甲", "乙"}


def test_concurrent_file_edits_are_serialized(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    course = client.post("/接口/课程", json={"name": "并发资料课"}).json()
    uploaded = client.post(
        f"/接口/课程/{course['id']}/资料",
        data={"title": "原名"},
        files={"file": ("a.txt", b"a", "text/plain")},
    ).json()
    assert uploaded["version"] == 1

    first = create_client()
    login_admin(first)
    second = create_client()
    login_admin(second)

    def edit(session, title):
        return session.patch(
            f"/接口/资料/{uploaded['id']}", json={"title": title, "version": 1}
        )

    responses = _run_together(edit, (first, "甲"), (second, "乙"))
    assert sorted(response.status_code for response in responses) == [200, 409]

    files = client.get(f"/接口/课程/{course['id']}/资料").json()["items"]
    assert files[0]["version"] == 2


def test_admin_retention_is_atomic(tmp_path, monkeypatch):
    """两个管理员同时把对方降权，绝不能把管理员清零。

    走 HTTP 时，被降权的一方可能在鉴权阶段就失去管理员权限，状态码会随调度漂移。
    这里直接调 `apply_user_update`，并让双方都先读到「有两个管理员」再更新，
    确定性地命中「先查后写」的竞态窗口。
    """

    from fastapi import HTTPException

    import app.api.users as users_api
    from app.db import configure_connection
    from app.schemas import UserUpdate

    client = _setup(tmp_path, monkeypatch)
    admin_id = client.get("/接口/当前用户").json()["id"]
    second = client.post(
        "/接口/用户",
        json={"username": "admin2", "password": "admin2-pass", "role": "admin"},
    ).json()

    real_fetch = users_api.fetch_user
    barrier = threading.Barrier(2)
    seen: set[threading.Thread] = set()

    def sync_fetch(user_id, db):
        row = real_fetch(user_id, db)
        thread = threading.current_thread()
        if thread not in seen:
            seen.add(thread)
            barrier.wait()
        return row

    monkeypatch.setattr(users_api, "fetch_user", sync_fetch)

    database = str(tmp_path / "test.db")
    conn1 = sqlite3.connect(database, check_same_thread=False)
    conn2 = sqlite3.connect(database, check_same_thread=False)
    configure_connection(conn1)
    configure_connection(conn2)

    def demote(conn, target_id, actor_id):
        try:
            users_api.apply_user_update(
                target_id, UserUpdate(role="viewer"), {"id": actor_id}, conn
            )
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result()
            for future in [
                pool.submit(demote, conn1, second["id"], admin_id),
                pool.submit(demote, conn2, admin_id, second["id"]),
            ]
        ]
    conn1.close()
    conn2.close()

    assert sorted(results) == [200, 409]
    # 直接查库：竞态后原管理员可能已被降权，用 HTTP 查会 403。
    check = sqlite3.connect(database)
    admins = check.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'"
    ).fetchone()[0]
    check.close()
    assert admins == 1


def test_course_quota_is_atomic_under_concurrency(tmp_path, monkeypatch):
    client = _setup(
        tmp_path,
        monkeypatch,
        COURSEBOX_MAX_COURSE_BYTES="10",
        COURSEBOX_MAX_FILE_SIZE="100",
    )
    course = client.post("/接口/课程", json={"name": "配额课"}).json()

    first = create_client()
    login_admin(first)
    second = create_client()
    login_admin(second)

    def upload(session, name):
        return session.post(
            f"/接口/课程/{course['id']}/资料",
            data={"title": name},
            files={"file": (f"{name}.txt", b"x" * 8, "text/plain")},
        )

    # 课程配额 10 字节，同时各传 8 字节：只能成功一个。
    responses = _run_together(upload, (first, "甲"), (second, "乙"))
    assert sorted(response.status_code for response in responses) == [201, 413]

    quota = client.get(f"/接口/课程/{course['id']}/配额").json()
    assert quota["course_used"] == 8
