"""对已启动的服务做端到端冒烟。

用法：
    python scripts/smoke.py --base-url http://127.0.0.1:8000

只依赖标准库，不引入额外测试框架；任何一项不通过就以非零码退出，供 CI 使用。
TestClient 会绕过真实的 HTTP 栈（例如中间件顺序、路由抢占），所以这里起真实服务再打一遍。
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SECONDS = 10


def call(base_url: str, path: str, method: str = "GET", headers: dict | None = None):
    url = base_url.rstrip("/") + urllib.parse.quote(path)
    request = urllib.request.Request(url, method=method, headers=headers or {})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def run(base_url: str) -> list[str]:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"ok   {name}")
        else:
            print(f"FAIL {name} {detail}")
            failures.append(name)

    status, body = call(base_url, "/api/health")
    check("健康检查 200", status == 200, f"got {status}")
    payload = json.loads(body) if body else {}
    check("健康检查 app=CourseBox", payload.get("app") == "CourseBox")

    status, body = call(base_url, "/")
    check("首页 200", status == 200, f"got {status}")
    check("首页含搜索框", b'id="search-form"' in body)

    status, body = call(base_url, "/接口/课程")
    check("课程列表 200", status == 200, f"got {status}")

    status, body = call(base_url, "/接口定义")
    check("OpenAPI 定义 200", status == 200, f"got {status}")

    # 未登录建课必须被挡。
    status, body = call(
        base_url,
        "/接口/课程",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    check("未登录建课 401", status == 401, f"got {status}")

    # 接口路径不存在：回统一 JSON。
    status, body = call(base_url, "/接口/不存在", headers={"Accept": "application/json"})
    check("未知接口 404", status == 404, f"got {status}")
    check("未知接口回 JSON", b"not_found" in body)

    # 浏览器访问未知页面：回中文错误页。
    status, body = call(base_url, "/不存在", headers={"Accept": "text/html"})
    check("未知页面回 HTML", b"text/html" in body or b"<!doctype" in body.lower())

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CourseBox 端到端冒烟")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)

    failures = run(args.base_url)
    if failures:
        print(f"\n冒烟失败：{len(failures)} 项 -> {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\n冒烟全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
