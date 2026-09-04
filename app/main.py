from fastapi import FastAPI

app = FastAPI(title="CourseBox 课盒子")


@app.get("/")
def health_check():
    return {"app": "CourseBox", "status": "ok", "docs": "/docs"}

