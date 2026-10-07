import re
from pathlib import Path

from conftest import _iter_api_routes, _route_shape

from app.main import app


def _frontend_api_calls(source: str) -> list[tuple[str, str]]:
    """从 app.js 里抽出所有指向 /api 的 fetch 调用，返回 (方法, 路径) 列表。"""
    pattern = re.compile(r"fetch\(\s*(?:\"([^\"]*)\"|`([^`]*)`)")
    matches = list(pattern.finditer(source))
    calls: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        raw = match.group(1) or match.group(2) or ""
        path = raw.split("?")[0]
        if not path.startswith("/api"):
            continue
        # method 只在这条 fetch 到下一条 fetch 之间找，否则会把后面的调用算到前面。
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        method_match = re.search(r"method:\s*\"([A-Z]+)\"", source[match.end() : end])
        method = method_match.group(1) if method_match else "GET"
        calls.append((method, path))
    return calls


def test_frontend_fetch_calls_match_registered_routes():
    """app.js 里每个 fetch 的「路径 + 方法」都必须在后端真实存在。

    回归背景：批量审核在后端因为路由注册顺序从 PATCH 改成了 POST，
    但 app.js 忘了跟着改，线上点「批量通过 / 批量拒绝」会拿到 405。
    pytest 打的是接口，前端 JS 平时不在测试范围内，所以这条专盯两者的接缝。
    """
    routes: dict[str, set[str]] = {}
    for route in _iter_api_routes(app):
        routes.setdefault(_route_shape(route.path), set()).update(
            route.methods - {"HEAD", "OPTIONS"}
        )
    # 后端路由表本身要能解析出来，否则下面的比对会「因为空所以全过」。
    assert routes.get("/api/courses") == {"GET", "POST"}, sorted(routes)

    source = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    calls = _frontend_api_calls(source)
    assert calls, "没从 app.js 解析出任何 /api 调用，解析规则可能已过期"
    assert ("POST", "/api/files/batch/review") in calls

    problems = []
    for method, path in calls:
        allowed = routes.get(_route_shape(path))
        if allowed is None:
            problems.append(f"{method} {path} —— 后端没有这个路径")
        elif method not in allowed:
            problems.append(
                f"{method} {path} —— 后端只允许 {'/'.join(sorted(allowed))}"
            )
    assert not problems, "前端调用了后端不接受的接口：\n" + "\n".join(sorted(set(problems)))


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _static_pages() -> dict[str, str]:
    return {
        name: (STATIC_DIR / name).read_text(encoding="utf-8")
        for name in ("index.html", "course.html")
    }


def test_frontend_element_ids_exist_in_some_page():
    """app.js 里 querySelector("#id") 用到的每个 id，至少要出现在一个页面里。

    回归背景：改密码入口最初只加在 index.html，course.html 漏了；两页共用同一个
    app.js，少了元素不会报错、只会「点了没反应」，肉眼很难发现。
    """

    pages = _static_pages()
    source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'querySelector\("#([A-Za-z0-9_-]+)"\)', source))
    assert ids, "没从 app.js 解析出任何 id，正则可能已过期"

    missing = sorted(
        element_id
        for element_id in ids
        if not any(f'id="{element_id}"' in html for html in pages.values())
    )
    assert not missing, f"app.js 引用了任何页面都没有的 id：{missing}"


def test_both_pages_share_the_auth_controls():
    """登录 / 改密码的控件两页必须都有，否则入口会随页面而消失。"""

    required = (
        "auth-status",
        "login-toggle",
        "password-toggle",
        "logout-button",
        "login-panel",
        "login-form",
        "login-message",
        "password-panel",
        "password-form",
        "password-message",
    )
    for name, html in _static_pages().items():
        missing = [element_id for element_id in required if f'id="{element_id}"' not in html]
        assert not missing, f"{name} 缺少登录 / 改密码控件：{missing}"
