import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.db import UPLOADS_PATH, get_db


MAX_FILE_SIZE = 20 * 1024 * 1024
router = APIRouter(tags=["资料"])


def course_exists(course_id: int, db: sqlite3.Connection) -> bool:
    row = db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
    return row is not None


def file_response(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "title": row["title"],
        "original_name": row["original_name"],
        "size": row["size"],
        "upload_time": row["upload_time"],
    }


def search_response(row: sqlite3.Row) -> dict:
    result = file_response(row)
    result["course"] = {
        "id": row["course_id"],
        "name": row["course_name"],
        "college": row["college"],
        "semester": row["semester"],
    }
    return result


@router.get("/api/courses/{course_id}/files", include_in_schema=False)
@router.get(
    "/接口/课程/{course_id}/资料",
    summary="查看课程资料",
    operation_id="查看课程资料",
)
def list_course_files(
    course_id: int, db: sqlite3.Connection = Depends(get_db)
) -> list[dict]:
    if not course_exists(course_id, db):
        raise HTTPException(status_code=404, detail="课程不存在")

    rows = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time
        FROM files WHERE course_id = ? ORDER BY id DESC
        """,
        (course_id,),
    ).fetchall()
    return [file_response(row) for row in rows]


@router.post(
    "/api/courses/{course_id}/files",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/接口/课程/{course_id}/资料",
    status_code=status.HTTP_201_CREATED,
    summary="上传课程资料",
    operation_id="上传课程资料",
)
async def upload_course_file(
    course_id: int,
    title: str = Form(..., title="资料标题"),
    file: UploadFile = File(..., title="资料文件"),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    if not course_exists(course_id, db):
        raise HTTPException(status_code=404, detail="课程不存在")

    title = title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="资料标题不能为空")

    original_name = Path(file.filename or "未命名文件").name
    suffix = Path(original_name).suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOADS_PATH / stored_name
    size = 0

    try:
        with stored_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="文件不能超过 20MB")
                output.write(chunk)
    except HTTPException:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    cursor = db.execute(
        """
        INSERT INTO files (course_id, title, filename, original_name, size)
        VALUES (?, ?, ?, ?, ?)
        """,
        (course_id, title, stored_name, original_name, size),
    )
    db.commit()
    row = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time
        FROM files WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return file_response(row)


download_router = APIRouter(tags=["资料"])


@download_router.get("/api/files/{file_id}/download", include_in_schema=False)
@download_router.get(
    "/接口/资料/{file_id}/下载",
    summary="下载资料",
    operation_id="下载资料",
)
def download_file(file_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        "SELECT filename, original_name FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")

    path = UPLOADS_PATH / row["filename"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=row["original_name"])


search_router = APIRouter(tags=["搜索"])


@search_router.get("/api/search", include_in_schema=False)
@search_router.get(
    "/接口/搜索",
    summary="搜索资料",
    operation_id="搜索资料",
)
def search_files(
    request: Request,
    关键词: str = "",
    db: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    keyword = (关键词 or request.query_params.get("q", "")).strip()
    if not keyword:
        return []

    pattern = f"%{keyword}%"
    rows = db.execute(
        """
        SELECT f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
               c.name AS course_name, c.college, c.semester, f.filename
        FROM files AS f
        JOIN courses AS c ON c.id = f.course_id
        WHERE LOWER(f.title) LIKE LOWER(?)
           OR LOWER(f.original_name) LIKE LOWER(?)
           OR LOWER(c.name) LIKE LOWER(?)
        ORDER BY f.id DESC
        """,
        (pattern, pattern, pattern),
    ).fetchall()
    return [search_response(row) for row in rows]
