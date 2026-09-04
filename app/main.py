from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.courses import router as courses_router
from app.api.files import download_router, router as files_router, search_router

app = FastAPI(
    title="CourseBox 课盒子",
    docs_url="/接口文档",
    redoc_url="/接口说明",
    openapi_url="/接口定义",
    swagger_ui_oauth2_redirect_url="/接口文档/授权回调",
)
app.include_router(courses_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(search_router)

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
def course_page():
    return FileResponse(STATIC_PATH / "course.html")


@app.get(
    "/接口/健康",
    summary="健康检查",
    operation_id="健康检查",
)
def health_check():
    return {
        "app": "CourseBox",
        "status": "ok",
        "docs": "/接口文档",
        "应用": "课盒子",
        "状态": "正常",
        "文档": "/接口文档",
    }


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

    schema_titles = {
        "Course": "课程",
        "CourseCreate": "课程创建请求",
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
                "title": "资料标题",
                "file": "资料文件",
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
