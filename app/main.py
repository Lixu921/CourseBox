from fastapi import FastAPI

from app.api.courses import router as courses_router
from app.api.files import download_router, router as files_router, search_router

app = FastAPI(title="CourseBox 课盒子")
app.include_router(courses_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(search_router)


@app.get("/")
def health_check():
    return {"app": "CourseBox", "status": "ok", "docs": "/docs"}
