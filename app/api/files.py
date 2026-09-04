import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.db import UPLOADS_PATH, get_db


MAX_FILE_SIZE = 20 * 1024 * 1024
router = APIRouter(prefix="/api/courses", tags=["files"])


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


@router.get("/{course_id}/files")
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


@router.post("/{course_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_course_file(
    course_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
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

