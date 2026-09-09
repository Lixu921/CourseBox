import json
import logging
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.files import download_router, search_router
from app.api.files import router as files_router
from app.config import database_path, get_settings, uploads_path
from app.db import cleanup_staged_files, get_db, init_db


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

app = FastAPI(
    title="CourseBox 课盒子",
    docs_url="/接口文档",
    redoc_url="/接口说明",
    openapi_url="/接口定义",
    swagger_ui_oauth2_redirect_url="/接口文档/授权回调",
)
init_db()
startup_db_generator = get_db()
startup_db = next(startup_db_generator)
try:
    cleanup_staged_files(startup_db)
finally:
    startup_db_generator.close()
app.include_router(courses_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(search_router)
app.include_router(auth_router)


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id_for(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "")
    return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid.uuid4().hex


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


def error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        422: "validation_error",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, "request_error")


def request_error_response(
    request: Request,
    status_code: int,
    detail: object,
    message: str | None = None,
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
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return request_error_response(request, exc.status_code, exc.detail)


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


@app.get("/资源/样式.css", include_in_schema=False)
def stylesheet():
    return FileResponse(STATIC_PATH / "style.css", media_type="text/css")


@app.get("/资源/脚本.js", include_in_schema=False)
def script():
    return FileResponse(STATIC_PATH / "app.js", media_type="text/javascript")


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(STATIC_PATH / "index.html")


@app.get("/课程", include_in_schema=False)
@app.get("/course", include_in_schema=False)
def course_page():
    return FileResponse(STATIC_PATH / "course.html")


@app.get(
    "/接口/健康",
    summary="健康检查",
    operation_id="健康检查",
)
def health_check():
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
    if not healthy:
        return JSONResponse(status_code=503, content=result)
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
        logger.warning(
            "database health check failed",
            extra={"event": "health_check", "request_id": None},
        )
        return {"status": "error", "message": str(error)}
    finally:
        if connection is not None:
            connection.close()


def check_uploads_directory() -> dict:
    path = uploads_path()
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            return {"status": "error", "message": "上传目录不是文件夹"}
        probe = tempfile.NamedTemporaryFile(dir=path, prefix=".health-", delete=False)
        probe_path = Path(probe.name)
        probe.close()
        probe_path.unlink(missing_ok=True)
        return {"status": "ok"}
    except OSError as error:
        return {"status": "error", "message": str(error)}


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
        return {"status": "error", "message": str(error)}


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

    for path, path_item in list(schema["paths"].items()):
        localized_path = path.replace("{course_id}", "{课程编号}").replace(
            "{file_id}", "{资料编号}"
        )
        if localized_path != path:
            schema["paths"][localized_path] = schema["paths"].pop(path)
        for operation in schema["paths"][localized_path].values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                if parameter.get("name") == "course_id":
                    parameter["name"] = "课程编号"
                    parameter.setdefault("schema", {})["title"] = "课程编号"
                elif parameter.get("name") == "file_id":
                    parameter["name"] = "资料编号"
                    parameter.setdefault("schema", {})["title"] = "资料编号"
                elif parameter.get("name") == "coursebox_session":
                    parameter["name"] = "会话令牌"
                    parameter.setdefault("schema", {})["title"] = "会话令牌"

    schema_titles = {
        "Course": "课程",
        "CourseCreate": "课程创建请求",
        "CourseUpdate": "课程更新请求",
        "CourseDetail": "课程详情",
        "FileUpdate": "资料更新请求",
        "LoginRequest": "登录请求",
        "UserCreate": "用户创建请求",
        "User": "用户",
        "FileReview": "资料审核请求",
        "PageInfo": "分页信息",
        "CoursePage": "课程分页响应",
        "FilePage": "资料分页响应",
        "HTTPValidationError": "请求校验错误",
        "ValidationError": "字段校验错误",
    }
    schemas = schema.get("components", {}).get("schemas", {})
    schema_names = {
        **{name: title for name, title in schema_titles.items()},
        **{
            name: "资料上传请求"
            for name in schemas
            if name.startswith("Body_")
        },
    }

    def replace_schema_references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref" and isinstance(item, str):
                    for old_name, new_name in schema_names.items():
                        item = item.replace(
                            f"#/components/schemas/{old_name}",
                            f"#/components/schemas/{new_name}",
                        )
                    value[key] = item
                else:
                    replace_schema_references(item)
        elif isinstance(value, list):
            for item in value:
                replace_schema_references(item)

    replace_schema_references(schema)

    localized_schemas = {}
    for schema_name, schema_body in schemas.items():
        localized_name = schema_names.get(schema_name, schema_name)
        if schema_name in schema_titles:
            schema_body["title"] = schema_titles[schema_name]
        elif schema_name.startswith("Body_"):
            schema_body["title"] = "资料上传请求"
        for property_name, property_body in schema_body.get("properties", {}).items():
            property_titles = {
                "id": "编号",
                "name": "名称",
                "college": "学院",
                "semester": "学期",
                "file_count": "资料数量",
                "title": "资料标题",
                "file": "资料文件",
                "username": "用户名",
                "password": "密码",
                "role": "角色",
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
            }
            if property_name in property_titles:
                property_body["title"] = property_titles[property_name]
        localized_schemas[localized_name] = schema_body

    schema["components"]["schemas"] = localized_schemas

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = localized_openapi
