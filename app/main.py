import hashlib
import json
import logging
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.auth import set_session_cookie
from app.api.comments import router as comments_router
from app.api.courses import router as courses_router
from app.api.files import download_router, search_router, trash_router
from app.api.files import router as files_router
from app.api.insights import router as insights_router
from app.api.share import router as share_router
from app.api.users import router as users_router
from app.config import database_path, get_settings, uploads_path
from app.db import (
    HEALTH_PROBE_PREFIX,
    LOGIN_ATTEMPT_RETENTION_SECONDS,
    checkpoint_wal,
    cleanup_health_probes,
    cleanup_staged_files,
    get_db,
    init_db,
    purge_audit_logs,
    purge_deleted_files,
    purge_expired_sessions,
    purge_login_attempts,
)
from app.ratelimit import EXEMPT_PATHS, client_key, rate_limiter


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("event", "request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("coursebox")


def configure_logging() -> None:
    logger.setLevel(get_settings().log_level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


configure_logging()

# 配置错误（例如生产环境缺少管理员密码）必须在这里直接抛出，不能带着默认密码启动。
initial_settings = get_settings()

# 建表与迁移是幂等的，也不删任何磁盘文件，留在导入时执行没有副作用。
init_db()


def run_startup_maintenance() -> None:
    """启动维护：清掉残留的暂存文件与健康检查探针，并按保留期清理数据。

    刻意放在 lifespan 里而不是模块导入时执行：导入 app.main 只是「加载代码」，
    不该顺手删磁盘文件、清数据库。否则测试收集、文档工具、linter 之类只要 import
    一次就会触发一遍破坏性维护，既意外又难排查。
    """
    generator = get_db()
    connection = next(generator)
    try:
        cleanup_staged_files(connection)
        # 健康检查的探针文件正常建完就删，删不掉时会残留，启动时顺手清一遍。
        cleanup_health_probes()
        settings = get_settings()
        purge_audit_logs(connection, settings.audit_retention_days)
        purge_login_attempts(connection, LOGIN_ATTEMPT_RETENTION_SECONDS)
        # 过期会话只在这里和 py -m app.maintenance 里清理，不挂在读请求上。
        purge_expired_sessions(connection)
        # 顺手做一次 WAL 合并，避免 -wal 文件随写入只涨不落。
        checkpoint_wal(connection)
        # 回收站里超过保留期的资料在这里真正从磁盘删除。放在启动时做，配合定时任务
        # （py -m app.maintenance）覆盖长期不重启的部署。
        purge_deleted_files(connection, settings.trash_retention_days)
    finally:
        generator.close()


@asynccontextmanager
async def lifespan(application: FastAPI):
    run_startup_maintenance()
    yield


app = FastAPI(
    title="CourseBox 课盒子",
    # 生产环境可用 COURSEBOX_ENABLE_DOCS=false 关闭接口文档与 OpenAPI 定义。
    docs_url="/接口文档" if initial_settings.enable_docs else None,
    redoc_url="/接口说明" if initial_settings.enable_docs else None,
    openapi_url="/接口定义" if initial_settings.enable_docs else None,
    swagger_ui_oauth2_redirect_url=(
        "/接口文档/授权回调" if initial_settings.enable_docs else None
    ),
    lifespan=lifespan,
)
app.include_router(courses_router)
app.include_router(comments_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(search_router)
app.include_router(trash_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(share_router)
app.include_router(insights_router)


class BodySizeLimitMiddleware:
    """在 ASGI 层包裹 receive，按实际读到的字节数限制请求体。

    上面的 HTTP 中间件只能看 Content-Length；分块传输没有这个头。这里直接数流过的
    字节，超限就抛 413 的 HTTPException。

    两点关键：
    - 必须抛 FastAPI 自己的 HTTPException：FastAPI 读取请求体时只把它的 HTTPException
      原样再抛，其它异常会被改写成 400。
    - 注册顺序必须最早，让它成为最内层用户中间件。若它和 FastAPI 之间还夹着
      BaseHTTPMiddleware（@app.middleware 装饰的那些），异常会被那一层吞掉。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_request_bytes
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="请求内容过大")
            return message

        await self.app(scope, limited_receive, send)


# 先注册它，才会落在最内层（add_middleware 是「后注册的在外层」）。
app.add_middleware(BodySizeLimitMiddleware)


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id_for(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "")
    return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid.uuid4().hex


# 全站兜底的安全响应头。用 setdefault 而非直接赋值：预览接口会按文件类型
# 自己设更严格的 CSP，不能被这里覆盖掉。
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # 在线预览靠同源 iframe 承载，所以只能是 SAMEORIGIN，不能用 DENY。
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    # 站点不需要摄像头/麦克风/定位等能力，直接全部关掉。
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# 页面没有内联脚本、没有内联样式、也没有外部 CDN，所以 CSP 可以收紧到只允许同源。
PAGE_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self'; "
    "script-src 'self'; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'"
)

# 接口文档（Swagger UI / ReDoc）是 FastAPI 自带页面：脚本与样式来自 CDN，且含一段内联
# 初始化脚本。用 PAGE_CSP 会把两者都拦掉、页面白屏，所以这两个前缀改用下面的策略。
DOCS_PATH_PREFIXES = ("/接口文档", "/接口说明")
DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'self'"
)


# 注意中间件顺序：Starlette 里「后注册的在最外层」，所以下面两个必须写在
# request_logging_middleware 之前，限流返回的 429 才会带上 request_id 与安全头。
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    settings = get_settings()
    if not settings.rate_limit_enabled or request.url.path in EXEMPT_PATHS:
        return await call_next(request)

    allowed, retry_after = rate_limiter.hit(
        client_key(request), settings.rate_limit_per_minute
    )
    if allowed:
        return await call_next(request)

    request_id = getattr(request.state, "request_id", "")
    logger.warning(
        "rate limit exceeded",
        extra={
            "event": "rate_limited",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client": client_key(request),
        },
    )
    message = "请求过于频繁，请稍后再试"
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": {
                "code": "too_many_requests",
                "message": message,
                "request_id": request_id,
            },
            "detail": message,
        },
        headers={"Retry-After": str(retry_after)},
    )


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """在解析请求体之前挡掉超大上传。

    Starlette 会先把整个 multipart body 落盘、再进入端点，端点的 413 来得太晚，
    超大文件已经消耗了磁盘与带宽。这里只认 Content-Length：超限的请求根本不进入
    端点。分块传输（没有该头）仍需反向代理兜底，见 README「已知局限」。

    注册次序在 security_headers_middleware 之前，这样它返回的 413 也会经过安全头
    中间件；request_id 由更外层的 request_logging_middleware 补上。
    """

    limit = get_settings().max_request_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "request body too large",
            extra={
                "event": "payload_too_large",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        message = "请求内容过大"
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "payload_too_large",
                    "message": message,
                    "request_id": request_id,
                },
                "detail": message,
            },
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    # CSP 只加给 HTML 页面：文件下载与预览各自带媒体类型，加 CSP 可能干扰
    # 浏览器内置的 PDF/图片查看器。接口文档用允许 CDN 的专用策略，否则会白屏。
    if response.headers.get("content-type", "").startswith("text/html"):
        csp = (
            DOCS_CSP
            if request.url.path.startswith(DOCS_PATH_PREFIXES)
            else PAGE_CSP
        )
        response.headers.setdefault("Content-Security-Policy", csp)
    # 生产环境一律加 HSTS；http 源下浏览器会忽略它，本地开发不受影响。
    if get_settings().is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# 静态资源的公开路径前缀（中文路径与兼容路径都算）。
STATIC_PATH_PREFIXES = ("/static/", "/资源/")
# 带版本号查询串的资源内容不会变，可以放心长期强缓存。
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# HTML 必须每次回源校验：它里面写着当前资源的版本号，缓存住就会一直指向旧资源。
PAGE_CACHE_CONTROL = "no-cache"


@app.middleware("http")
async def cache_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(STATIC_PATH_PREFIXES):
        # 只有带版本号的地址才敢长期缓存；内容一变版本号就变，不会拿到旧文件。
        if request.query_params.get("v"):
            response.headers.setdefault("Cache-Control", IMMUTABLE_CACHE)
        else:
            response.headers.setdefault("Cache-Control", PAGE_CACHE_CONTROL)
    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request_id_for(request)
    request.state.request_id = request_id
    started = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            "request completed",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code if response else 500,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


@app.middleware("http")
async def session_cookie_refresh_middleware(request: Request, call_next):
    """把「会话已顺延」这件事真正写进响应。

    滑动续期的判断和数据库更新在 current_user / optional_user 里完成，那里只往
    request.state 上记一笔。原因是下载、预览、打包这几个接口直接返回 FileResponse，
    而 FastAPI 对「端点自己返回 Response」的分支不会合并依赖里设的响应头，
    在依赖里 set_cookie 会被静默丢掉。放到最外层统一补，才能覆盖所有响应类型。
    """

    response = await call_next(request)
    token = getattr(request.state, "renewed_session_token", None)
    if token:
        set_session_cookie(response, token)
    return response


def error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "gone",
        413: "payload_too_large",
        415: "unsupported_media_type",
        422: "validation_error",
        429: "too_many_requests",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, "request_error")


def request_error_response(
    request: Request,
    status_code: int,
    detail: object,
    message: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    resolved_message = message or (detail if isinstance(detail, str) else "请求处理失败")
    body = {
        "error": {
            "code": error_code(status_code),
            "message": resolved_message,
            "request_id": request_id,
        },
        # Keep detail for existing clients while all new clients can use error.
        "detail": jsonable_encoder(detail),
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


# 处理器必须挂在 Starlette 的基类上：路由未命中和静态文件 404 抛的都是基类异常，
# 只注册 FastAPI 的子类会让这些响应退回默认形状。
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 浏览器直接访问地址栏时给一张中文页面；接口调用方继续拿 JSON。
    if wants_html_error(request):
        return render_error_page(exc.status_code, error_page_message(exc))
    return request_error_response(
        request,
        exc.status_code,
        exc.detail,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return request_error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        exc.errors(),
        "请求参数校验失败",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled application error",
        extra={
            "event": "unhandled_error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return request_error_response(
        request, status.HTTP_500_INTERNAL_SERVER_ERROR, "服务器内部错误"
    )


STATIC_PATH = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="legacy-static")

# 参与版本号计算的资源文件。任何一个变了，页面里引用的地址就跟着变，从而绕过缓存。
# 前端按功能拆成 app.js / app-2.js / app-3.js 三段（经典脚本、共享全局作用域），
# 三个都要计入哈希，否则只改了后两段时入口版本号不变、浏览器会一直用旧的。
VERSIONED_ASSETS = ("style.css", "app.js", "app-2.js", "app-3.js")
# 页面里用占位符代替版本号，避免每次改资源都要手改 HTML。
ASSET_VERSION_PLACEHOLDER = "{{asset_version}}"

_asset_version: str | None = None
_page_cache: dict[str, str] = {}


def asset_version() -> str:
    """静态资源的内容指纹，取前 12 位十六进制；进程内只算一次。"""

    global _asset_version
    if _asset_version is None:
        digest = hashlib.sha256()
        for name in VERSIONED_ASSETS:
            try:
                digest.update((STATIC_PATH / name).read_bytes())
            except OSError:
                # 文件读不到时也要给一个稳定值，不能因为资源缺失就让页面打不开。
                digest.update(name.encode("utf-8"))
        _asset_version = digest.hexdigest()[:12]
    return _asset_version


def render_page(filename: str) -> HTMLResponse:
    """读取页面、把资源版本号填进占位符，并加上禁止缓存的响应头。"""

    version = asset_version()
    cache_key = f"{filename}:{version}"
    body = _page_cache.get(cache_key)
    if body is None:
        body = (STATIC_PATH / filename).read_text(encoding="utf-8")
        body = body.replace(ASSET_VERSION_PLACEHOLDER, version)
        _page_cache.clear()
        _page_cache[cache_key] = body
    return HTMLResponse(body, headers={"Cache-Control": PAGE_CACHE_CONTROL})


# 浏览器直接访问时的中文提示。接口调用方拿到的仍然是 JSON 错误结构。
ERROR_PAGE_MESSAGES = {
    400: "请求有误，请检查后重试。",
    401: "请先登录后再访问这个页面。",
    403: "你没有访问这个页面的权限。",
    404: "没有找到这个页面。",
    405: "这个地址不支持当前的访问方式。",
    409: "当前状态下无法完成这个操作。",
    413: "上传的内容太大了。",
    415: "不支持这种文件类型。",
    429: "请求太频繁了，请稍后再试。",
    500: "服务器开小差了，请稍后再试。",
    503: "服务暂时不可用，请稍后再试。",
}
# 这些前缀下的请求一律按接口对待，永远回 JSON，不回 HTML。
JSON_PATH_PREFIXES = ("/接口", "/api")


def wants_html_error(request: Request) -> bool:
    """这个请求是「浏览器直接打开地址」，还是接口调用？"""

    if request.url.path.startswith(JSON_PATH_PREFIXES):
        return False
    return "text/html" in request.headers.get("accept", "")


def error_page_message(exc: StarletteHTTPException) -> str:
    known = ERROR_PAGE_MESSAGES.get(exc.status_code)
    if known:
        return known
    # 没收录的状态码就用原始 detail，总比显示「未知错误」有用。
    if isinstance(exc.detail, str) and exc.detail:
        return exc.detail
    return "请求处理失败。"


def render_error_page(status_code: int, message: str) -> HTMLResponse:
    body = (STATIC_PATH / "error.html").read_text(encoding="utf-8")
    body = body.replace(ASSET_VERSION_PLACEHOLDER, asset_version())
    body = body.replace("{{status}}", str(status_code))
    # 错误信息可能来自 detail，必须转义后再拼进 HTML。
    body = body.replace("{{message}}", escape(message))
    return HTMLResponse(
        body, status_code=status_code, headers={"Cache-Control": PAGE_CACHE_CONTROL}
    )


@app.get("/资源/样式.css", include_in_schema=False)
def stylesheet():
    return FileResponse(STATIC_PATH / "style.css", media_type="text/css")


@app.get("/资源/脚本.js", include_in_schema=False)
def script():
    return FileResponse(STATIC_PATH / "app.js", media_type="text/javascript")


@app.get("/资源/脚本2.js", include_in_schema=False)
def script_part2():
    return FileResponse(STATIC_PATH / "app-2.js", media_type="text/javascript")


@app.get("/资源/脚本3.js", include_in_schema=False)
def script_part3():
    return FileResponse(STATIC_PATH / "app-3.js", media_type="text/javascript")


@app.get("/资源/图标.svg", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_PATH / "favicon.svg", media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    # 页面里已经声明了 SVG 图标，正常浏览器不会来请求这里；给一个空响应，
    # 免得旧书签或直接访问在日志里一直刷 404。
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/", include_in_schema=False)
def homepage():
    return render_page("index.html")


@app.get("/课程", include_in_schema=False)
@app.get("/course", include_in_schema=False)
def course_page():
    return render_page("course.html")


@app.get("/分享/{token}", include_in_schema=False)
def share_page(token: str):
    # token 由前端脚本从地址里取，这里只负责发页面。
    return render_page("share.html")


# 健康检查结果缓存。key 由库路径、上传目录、磁盘下限组成——测试与运行时常 monkeypatch
# 这些配置，用它们做 key 能保证换了配置就重新体检，而不是命中上一组配置的缓存。
_health_cache: dict[tuple[str, str, int], tuple[float, dict, int]] = {}


def reset_health_cache() -> None:
    """清空健康检查缓存。测试用例开始前调用，避免互相污染。"""

    _health_cache.clear()


def run_health_checks() -> tuple[dict, int]:
    checks = {
        "database": check_database(),
        "uploads": check_uploads_directory(),
        "disk": check_disk_space(),
    }
    healthy = all(item["status"] == "ok" for item in checks.values())
    result = {
        "app": "CourseBox",
        "status": "ok" if healthy else "degraded",
        "docs": "/接口文档",
        "checks": checks,
        "应用": "课盒子",
        "状态": "正常" if healthy else "异常",
        "文档": "/接口文档",
    }
    return result, 200 if healthy else 503


@app.get("/api/health", include_in_schema=False)
@app.get(
    "/接口/健康",
    summary="健康检查",
    operation_id="健康检查",
)
def health_check():
    settings = get_settings()
    key = (
        str(settings.database_path),
        str(settings.uploads_path),
        settings.min_free_space,
    )
    ttl = settings.health_cache_seconds
    if ttl > 0:
        cached = _health_cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < ttl:
            result, status_code = cached[1], cached[2]
            if status_code != 200:
                return JSONResponse(status_code=status_code, content=result)
            return result

    result, status_code = run_health_checks()
    if ttl > 0:
        _health_cache[key] = (time.monotonic(), result, status_code)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=result)
    return result


def check_database() -> dict:
    path = database_path()
    if not path.is_file():
        return {"status": "error", "message": "数据库文件不存在"}
    connection = None
    try:
        connection = sqlite3.connect(path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            return {"status": "error", "message": "数据库完整性检查失败"}
        required = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('courses', 'files')"
        ).fetchone()[0]
        if required != 2:
            return {"status": "error", "message": "数据库结构未初始化"}
        return {"status": "ok"}
    except (OSError, sqlite3.Error) as error:
        # 健康检查是公开接口，不能把异常原文（可能含数据库路径）返回给调用方；
        # 细节只写进结构化日志。
        logger.warning(
            "database health check failed: %s",
            error,
            extra={"event": "health_check", "request_id": None},
        )
        return {"status": "error", "message": "数据库健康检查失败"}
    finally:
        if connection is not None:
            connection.close()


def check_uploads_directory() -> dict:
    """确认上传目录真的可写。

    这里会真的建一个临时文件再删掉——只看目录权限位挡不住「只读挂载 / 磁盘写满」。
    但删除失败不算不健康：Windows 上杀毒软件偶尔会短暂占住刚建好的文件，
    为这个把整个实例判成不健康不划算。残留的探针交给启动时的
    cleanup_health_probes 兜底清理。
    """

    path = uploads_path()
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            return {"status": "error", "message": "上传目录不是文件夹"}
    except OSError as error:
        logger.warning(
            "uploads directory check failed: %s",
            error,
            extra={"event": "health_check", "request_id": None},
        )
        return {"status": "error", "message": "上传目录不可用"}

    try:
        probe = tempfile.NamedTemporaryFile(
            dir=path, prefix=HEALTH_PROBE_PREFIX, delete=False
        )
        probe_path = Path(probe.name)
        probe.close()
    except OSError as error:
        logger.warning(
            "uploads probe failed: %s",
            error,
            extra={"event": "health_check", "request_id": None},
        )
        return {"status": "error", "message": "上传目录不可写"}

    try:
        probe_path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning(
            "health probe cleanup failed: %s",
            error,
            extra={"event": "health_check", "request_id": None},
        )
    return {"status": "ok"}


def check_disk_space() -> dict:
    settings = get_settings()
    path = uploads_path()
    try:
        usage = shutil.disk_usage(path if path.exists() else Path.cwd())
        healthy = usage.free >= settings.min_free_space
        return {
            "status": "ok" if healthy else "error",
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "minimum_free_bytes": settings.min_free_space,
        }
    except OSError as error:
        logger.warning(
            "disk space check failed: %s",
            error,
            extra={"event": "health_check", "request_id": None},
        )
        return {"status": "error", "message": "磁盘空间检查失败"}


# 接口文档中文化。用「一组显式映射 + 按精确名替换 $ref」实现：
# - 旧实现用子串替换 $ref，`Course` 会先把 `CourseCreate` 改坏（变成「课程Create」）；
#   这里按组件全名精确映射，不再误伤。
# - 模型名、路径参数、属性标题各自一张表，新增模型时照着补一行即可。
OPENAPI_SCHEMA_TITLES = {
    "Course": "课程",
    "CourseCreate": "课程创建请求",
    "CourseUpdate": "课程更新请求",
    "CourseDetail": "课程详情",
    "CoursePage": "课程分页响应",
    "CourseQuota": "课程配额",
    "FileUpdate": "资料更新请求",
    "FileReview": "资料审核请求",
    "FilePage": "资料分页响应",
    "FileBatchReview": "批量审核请求",
    "LoginRequest": "登录请求",
    "RegisterRequest": "注册请求",
    "PasswordChange": "修改密码请求",
    "PasswordReset": "重置密码请求",
    "User": "用户",
    "UserAdmin": "用户详情",
    "UserCreate": "用户创建请求",
    "UserUpdate": "用户更新请求",
    "UserBatchUpdate": "批量修改用户请求",
    "UserPage": "用户分页响应",
    "BatchIds": "编号列表",
    "BatchItemResult": "批量结果项",
    "BatchResult": "批量结果",
    "PageInfo": "分页信息",
    "ShareCreate": "创建分享请求",
    "ShareLink": "分享链接",
    "ShareView": "分享内容",
    "TrashFile": "回收站资料",
    "TrashFilePage": "回收站分页响应",
    "AuditLog": "操作记录",
    "AuditLogPage": "操作记录分页响应",
    "InsightFile": "概览资料",
    "InsightFileList": "概览资料列表",
    "OverviewFiles": "资料数量",
    "Overview": "站点概览",
    "SessionInfo": "登录会话",
    "SessionList": "登录会话列表",
    "Comment": "评论",
    "CommentCreate": "发表评论请求",
    "CommentPage": "评论分页响应",
    "HTTPValidationError": "请求校验错误",
    "ValidationError": "字段校验错误",
}
OPENAPI_BODY_TITLE = "资料上传请求"
OPENAPI_PATH_PARAM_TITLES = {
    "course_id": "课程编号",
    "file_id": "资料编号",
    "share_id": "分享编号",
    "session_id": "会话编号",
    "token": "令牌",
    "coursebox_session": "会话令牌",
}
OPENAPI_PROPERTY_TITLES = {
    "id": "编号",
    "name": "名称",
    "college": "学院",
    "version": "版本号",
    "tags": "标签",
    "file_count": "资料数量",
    "title": "资料标题",
    "file": "资料文件",
    "original_name": "原文件名",
    "size": "大小",
    "upload_time": "上传时间",
    "username": "用户名",
    "password": "密码",
    "role": "角色",
    "is_active": "是否启用",
    "created_at": "创建时间",
    "upload_count": "上传资料数",
    "status": "状态",
    "uploaded_by": "上传者",
    "mime_type": "MIME 类型",
    "sha256": "SHA-256 哈希",
    "detail": "错误详情",
    "loc": "位置",
    "msg": "错误信息",
    "type": "错误类型",
    "input": "输入内容",
    "ctx": "错误上下文",
    "allowed_bytes": "本次允许字节数",
    "reason": "受限原因",
    "max_file_size": "单文件上限",
    "course_limit": "课程上限",
    "course_used": "课程已用",
    "course_remaining": "课程剩余",
    "site_limit": "站点上限",
    "site_used": "站点已用",
    "site_remaining": "站点剩余",
    "user_limit": "我的上限",
    "user_used": "我的已用",
    "user_remaining": "我的剩余",
    "disk_free": "磁盘剩余",
    "download_count": "下载次数",
    "comment_count": "评论数",
    "body": "评论内容",
    "current": "当前设备",
    "user_agent": "浏览器标识",
    "ip": "来源 IP",
    "approved": "已通过",
    "pending": "待审核",
    "rejected": "已拒绝",
    "courses": "课程数",
    "trash": "回收站",
    "users_total": "用户总数",
    "users_active": "启用用户",
    "storage_bytes": "存储用量",
    "downloads": "下载总数",
    "days": "有效天数",
    "note": "备注",
    "token": "令牌",
    "url": "链接",
    "expires_at": "过期时间",
    "files": "资料列表",
    "course": "课程",
    "items": "列表",
    "total": "总数",
    "page": "页码",
    "page_size": "每页数量",
    "total_pages": "总页数",
}

OPENAPI_REF_PREFIX = "#/components/schemas/"


def _localize_paths(schema: dict) -> None:
    for path in list(schema["paths"]):
        localized = path
        for old_name, title in OPENAPI_PATH_PARAM_TITLES.items():
            localized = localized.replace("{" + old_name + "}", "{" + title + "}")
        if localized != path:
            schema["paths"][localized] = schema["paths"].pop(path)
        for operation in schema["paths"][localized].values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                title = OPENAPI_PATH_PARAM_TITLES.get(parameter.get("name"))
                if title:
                    parameter["name"] = title
                    parameter.setdefault("schema", {})["title"] = title


def _localize_references(value: object, names: dict[str, str]) -> None:
    """按组件全名精确映射 $ref，避免子串替换误伤（如 Course / CourseCreate）。"""

    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith(
                OPENAPI_REF_PREFIX
            ):
                component = item[len(OPENAPI_REF_PREFIX) :]
                if component in names:
                    value[key] = OPENAPI_REF_PREFIX + names[component]
            else:
                _localize_references(item, names)
    elif isinstance(value, list):
        for item in value:
            _localize_references(item, names)


def localized_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="课盒子接口",
        version="1.0.0",
        description="课盒子课程资料共享接口。",
        routes=app.routes,
    )
    schema["info"]["title"] = "课盒子接口"
    schema["info"]["description"] = "课盒子课程资料共享接口。"

    _localize_paths(schema)

    schemas = schema.get("components", {}).get("schemas", {})
    names = dict(OPENAPI_SCHEMA_TITLES)
    for name in schemas:
        if name.startswith("Body_"):
            names[name] = OPENAPI_BODY_TITLE

    _localize_references(schema, names)

    localized_schemas = {}
    for name, body in schemas.items():
        title = names.get(name)
        if title:
            body["title"] = title
        for property_name, property_body in body.get("properties", {}).items():
            property_title = OPENAPI_PROPERTY_TITLES.get(property_name)
            if property_title and isinstance(property_body, dict):
                property_body["title"] = property_title
        localized_schemas[names.get(name, name)] = body
    schema["components"]["schemas"] = localized_schemas

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = localized_openapi
