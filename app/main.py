from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.courses import router as courses_router
from app.api.files import download_router, router as files_router, search_router

app = FastAPI(title="CourseBox 课盒子")
app.include_router(courses_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(search_router)

STATIC_PATH = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(STATIC_PATH / "index.html")


@app.get("/course.html", include_in_schema=False)
def course_page():
    return FileResponse(STATIC_PATH / "course.html")


@app.get("/api/health")
def health_check():
    return {"app": "CourseBox", "status": "ok", "docs": "/docs"}
