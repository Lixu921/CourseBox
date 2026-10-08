"""测试公共部分：建客户端、登录、以及跨文件复用的辅助函数。

用例按域拆在 test_*.py 里，公共 helper 放在这里，各文件用
``from conftest import create_client, login_admin`` 取用——pytest 会把 tests/
加进 sys.path，所以这个导入是可靠的（注意 conftest 里的函数不会自动注入到
测试模块的命名空间，必须显式 import，这也让「谁用了什么」一眼可见）。

为什么必须有 create_client()：限流按客户端 IP 计数，而所有测试都来自同一个
TestClient 主机；建表缓存又按数据库路径记忆。两者都要清空，测试之间才不会互相影响。
"""

import re

from fastapi.testclient import TestClient

from app.db import reset_initialized_databases
from app.main import app, reset_health_cache
from app.ratelimit import reset_rate_limits


def create_client() -> TestClient:
    # 限流按客户端 IP 计数，而所有测试都来自同一个 TestClient 主机；
    # 建表缓存按数据库路径记忆。两者都要清空，测试之间才不会互相影响。
    # 健康检查结果也带缓存，不清会让「改了上传目录」的用例读到上一组结果。
    reset_rate_limits()
    reset_initialized_databases()
    reset_health_cache()
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


def _upload_named(client, course_id: int, title: str, filename: str, content: bytes) -> dict:
    response = client.post(
        f"/接口/课程/{course_id}/资料",
        data={"title": title},
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()
