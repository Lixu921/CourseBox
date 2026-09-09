import logging
import sqlite3
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.auth import optional_user, require_roles
from app.config import DEFAULT_MAX_FILE_SIZE, allowed_extensions, max_file_size, uploads_path
from app.db import (
    discard_staged_files,
    get_db,
    record_audit,
    restore_staged_files,
    stage_stored_files,
)
from app.schemas import FilePage, FileReview, FileUpdate


router = APIRouter(tags=["资料"])
logger = logging.getLogger("coursebox")
DANGEROUS_MIME_TYPES = {
    "application/vnd.microsoft.portable-executable",
    "application/x-bat",
    "application/x-csh",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-msdownload",
    "application/x-powershell",
    "application/x-sh",
    "text/x-shellscript",
}
DANGEROUS_EXTENSIONS = {
    ".apk",
    ".appx",
    ".bat",
    ".cmd",
    ".com",
    ".cpl",
    ".dll",
    ".dmg",
    ".exe",
    ".hta",
    ".jar",
    ".js",
    ".jse",
    ".msi",
    ".msp",
    ".ps1",
    ".pif",
    ".scr",
    ".sh",
    ".sys",
    ".vb",
    ".vbe",
    ".vbs",
    ".wsf",
    ".wsh",
}


def course_exists(course_id: int, db: sqlite3.Connection) -> bool:
    row = db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
    return row is not None


def file_response(row: sqlite3.Row) -> dict:
    result = {
        "id": row["id"],
        "course_id": row["course_id"],
        "title": row["title"],
        "original_name": row["original_name"],
        "size": row["size"],
        "upload_time": row["upload_time"],
    }
    for key in ("mime_type", "sha256", "status", "uploaded_by"):
        if key in row.keys():
            result[key] = row[key]
    return result


def search_response(row: sqlite3.Row) -> dict:
    result = file_response(row)
    result["course"] = {
        "id": row["course_id"],
        "name": row["course_name"],
        "college": row["college"],
        "semester": row["semester"],
    }
    return result


def page_response(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def stored_file_path(filename: str) -> Path | None:
    root = uploads_path().resolve()
    path = (root / filename).resolve()
    return path if root in path.parents else None


def fts_query(keyword: str) -> str:
    return " AND ".join(
        f'"{part.replace(chr(34), "")}"' for part in keyword.split() if part
    )


def remove_stored_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        # Cleanup must never replace the original API error.
        logger.warning(
            "stored file cleanup failed: %s",
            error,
            extra={"event": "file_cleanup"},
        )


@router.get("/api/courses/{course_id}/files", include_in_schema=False)
@router.get(
    "/接口/课程/{course_id}/资料",
    response_model=FilePage,
    summary="查看课程资料",
    operation_id="查看课程资料",
)
def list_course_files(
    course_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
) -> FilePage:
    if not course_exists(course_id, db):
        raise HTTPException(status_code=404, detail="课程不存在")

    visibility = "f.status = 'approved'"
    params: list[object] = [course_id]
    if user is not None and user["role"] == "admin":
        visibility = "1 = 1"
    elif user is not None and user["role"] == "uploader":
        visibility = "(f.status = 'approved' OR f.uploaded_by = ?)"
        params.append(user["id"])
    total = db.execute(
        f"SELECT COUNT(*) FROM files AS f WHERE f.course_id = ? AND {visibility}",
        params,
    ).fetchone()[0]
    params.extend([page_size, (page - 1) * page_size])
    rows = db.execute(
        f"""
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files AS f WHERE f.course_id = ? AND {visibility}
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()
    return FilePage(
        **page_response([file_response(row) for row in rows], total, page, page_size)
    )


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
    user: sqlite3.Row = Depends(require_roles("admin", "uploader")),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    stored_path: Path | None = None
    try:
        if not course_exists(course_id, db):
            raise HTTPException(status_code=404, detail="课程不存在")

        title = title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="资料标题不能为空")
        if len(title) > 200:
            raise HTTPException(status_code=422, detail="资料标题不能超过 200 个字符")

        if not file.filename or not file.filename.strip():
            raise HTTPException(status_code=422, detail="文件名不能为空")
        original_name = Path(file.filename).name
        suffix = Path(original_name).suffix
        if len(original_name) > 255:
            raise HTTPException(status_code=422, detail="文件名不能超过 255 个字符")
        normalized_suffix = suffix.lower()
        if normalized_suffix in DANGEROUS_EXTENSIONS:
            raise HTTPException(status_code=415, detail="不允许上传可执行文件")
        if normalized_suffix not in allowed_extensions():
            raise HTTPException(status_code=415, detail="暂不支持该文件类型")
        content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
        if content_type in DANGEROUS_MIME_TYPES:
            raise HTTPException(status_code=415, detail="不允许上传可执行文件")

        limit = max_file_size()
        upload_root = uploads_path().resolve()
        upload_root.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        stored_path = (upload_root / stored_name).resolve()
        if upload_root not in stored_path.parents:
            raise HTTPException(status_code=400, detail="无效的文件路径")

        size = 0
        digest = hashlib.sha256()
        with stored_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    detail = (
                        "文件不能超过 20MB"
                        if limit == DEFAULT_MAX_FILE_SIZE
                        else f"文件不能超过 {limit} 字节"
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=detail,
                    )
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="文件不能为空")

        try:
            cursor = db.execute(
                """
                INSERT INTO files
                    (course_id, title, filename, original_name, size, mime_type, sha256,
                     status, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    title,
                    stored_name,
                    original_name,
                    size,
                    content_type or None,
                    digest.hexdigest(),
                    "approved" if user["role"] == "admin" else "pending",
                    user["id"],
                ),
            )
            record_audit(
                db,
                user["id"],
                "upload",
                "file",
                cursor.lastrowid,
                f"上传资料 {original_name}",
            )
            db.commit()
        except sqlite3.IntegrityError as error:
            db.rollback()
            if "sha256" in str(error).lower():
                raise HTTPException(status_code=409, detail="该课程已存在相同文件") from error
            raise
        except Exception:
            db.rollback()
            raise
    except HTTPException:
        remove_stored_file(stored_path)
        raise
    except Exception:
        remove_stored_file(stored_path)
        db.rollback()
        raise
    finally:
        await file.close()

    row = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return file_response(row)


@router.patch(
    "/api/files/{file_id}",
    include_in_schema=False,
)
@router.patch(
    "/接口/资料/{file_id}",
    summary="编辑资料标题",
    operation_id="编辑资料标题",
)
def update_file(
    file_id: int,
    update: FileUpdate,
    user: sqlite3.Row = Depends(require_roles("admin", "uploader")),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    existing = db.execute(
        "SELECT uploaded_by FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if user["role"] != "admin" and existing["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="没有编辑此资料的权限")
    cursor = db.execute(
        "UPDATE files SET title = ? WHERE id = ?", (update.title, file_id)
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="资料不存在")
    record_audit(db, user["id"], "update", "file", file_id, "修改资料标题")
    db.commit()
    row = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files WHERE id = ?
        """,
        (file_id,),
    ).fetchone()
    return file_response(row)


@router.delete(
    "/api/files/{file_id}",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/接口/资料/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除资料",
    operation_id="删除资料",
)
def delete_file(
    file_id: int,
    user: sqlite3.Row = Depends(require_roles("admin", "uploader")),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute(
        "SELECT filename, uploaded_by FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if user["role"] != "admin" and row["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="没有删除此资料的权限")
    staged = stage_stored_files([row], db)
    try:
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        record_audit(db, user["id"], "delete", "file", file_id)
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_files(staged, db)
        raise
    discard_staged_files(staged, db)


download_router = APIRouter(tags=["资料"])


@download_router.get("/api/files/{file_id}/download", include_in_schema=False)
@download_router.get(
    "/接口/资料/{file_id}/下载",
    summary="下载资料",
    operation_id="下载资料",
)
def download_file(
    file_id: int,
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        """
        SELECT filename, original_name, mime_type, status, uploaded_by
        FROM files WHERE id = ?
        """,
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")

    if row["status"] != "approved":
        if user is None or (user["role"] != "admin" and user["id"] != row["uploaded_by"]):
            raise HTTPException(status_code=404, detail="资料不存在")
    path = stored_file_path(row["filename"])
    if path is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    record_audit(db, user["id"] if user else None, "download", "file", file_id)
    db.commit()
    return FileResponse(
        path,
        filename=row["original_name"],
        media_type=row["mime_type"] or "application/octet-stream",
    )


search_router = APIRouter(tags=["搜索"])


@search_router.get("/api/search", include_in_schema=False)
@search_router.get(
    "/接口/搜索",
    response_model=FilePage,
    summary="搜索资料",
    operation_id="搜索资料",
)
def search_files(
    request: Request,
    关键词: str = "",
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: sqlite3.Connection = Depends(get_db),
) -> FilePage:
    keyword = (关键词 or request.query_params.get("q", "")).strip()
    if not keyword:
        return FilePage(**page_response([], 0, page, page_size))

    pattern = f"%{keyword}%"
    match_query = fts_query(keyword)
    try:
        total = db.execute(
            """
            SELECT COUNT(*)
            FROM files_fts AS fts
            JOIN files AS f ON f.id = fts.rowid
            JOIN courses AS c ON c.id = f.course_id
            WHERE f.status = 'approved' AND (fts MATCH ?
               OR LOWER(f.title) LIKE LOWER(?)
               OR LOWER(f.original_name) LIKE LOWER(?)
               OR LOWER(c.name) LIKE LOWER(?))
            """,
            (match_query, pattern, pattern, pattern),
        ).fetchone()[0]
        rows = db.execute(
            """
            SELECT f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
                   f.mime_type, f.sha256, f.status,
                   c.name AS course_name, c.college, c.semester, f.filename
            FROM files_fts AS fts
            JOIN files AS f ON f.id = fts.rowid
            JOIN courses AS c ON c.id = f.course_id
            WHERE f.status = 'approved' AND (fts MATCH ?
               OR LOWER(f.title) LIKE LOWER(?)
               OR LOWER(f.original_name) LIKE LOWER(?)
               OR LOWER(c.name) LIKE LOWER(?))
            ORDER BY f.id DESC LIMIT ? OFFSET ?
            """,
            (
                match_query,
                pattern,
                pattern,
                pattern,
                page_size,
                (page - 1) * page_size,
            ),
        ).fetchall()
    except sqlite3.OperationalError:
        where = """
            f.status = 'approved' AND (LOWER(f.title) LIKE LOWER(?)
            OR LOWER(f.original_name) LIKE LOWER(?)
            OR LOWER(c.name) LIKE LOWER(?))
        """
        total = db.execute(
            f"SELECT COUNT(*) FROM files AS f JOIN courses AS c ON c.id = f.course_id WHERE {where}",
            (pattern, pattern, pattern),
        ).fetchone()[0]
        rows = db.execute(
            f"""
            SELECT f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
                   f.mime_type, f.sha256, f.status,
                   c.name AS course_name, c.college, c.semester, f.filename
            FROM files AS f JOIN courses AS c ON c.id = f.course_id
            WHERE {where} ORDER BY f.id DESC LIMIT ? OFFSET ?
            """,
            (pattern, pattern, pattern, page_size, (page - 1) * page_size),
        ).fetchall()
    return FilePage(
        **page_response([search_response(row) for row in rows], total, page, page_size)
    )


@router.patch(
    "/api/files/{file_id}/review",
    include_in_schema=False,
)
@router.patch(
    "/接口/资料/{file_id}/审核",
    response_model=dict,
    summary="审核资料",
    operation_id="审核资料",
)
def review_file(
    file_id: int,
    review: FileReview,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    cursor = db.execute(
        "UPDATE files SET status = ? WHERE id = ?",
        (review.status, file_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="资料不存在")
    record_audit(
        db,
        user["id"],
        review.status,
        "file",
        file_id,
        f"资料审核结果：{review.status}",
    )
    db.commit()
    row = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files WHERE id = ?
        """,
        (file_id,),
    ).fetchone()
    return file_response(row)
