import hashlib
import logging
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.auth import current_user, optional_user, require_roles
from app.api.common import escape_like, page_response, parse_date
from app.config import PROJECT_ROOT, allowed_extensions, get_settings, uploads_path
from app.db import (
    discard_staged_files,
    get_db,
    record_audit,
    restore_staged_files,
    stage_stored_files,
)
from app.schemas import (
    BatchItemResult,
    BatchResult,
    CourseQuota,
    FileBatchReview,
    FilePage,
    FileReview,
    FileUpdate,
    TrashFilePage,
)

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
# FTS5 的 trigram 分词器只索引长度不小于 3 的片段。
MIN_FTS_TERM_LENGTH = 3


def course_exists(course_id: int, db: sqlite3.Connection) -> bool:
    row = db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
    return row is not None


def format_bytes(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} GB"
    if size >= 1024**2:
        return f"{size / 1024**2:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} 字节"


def upload_quota(course_id: int, db: sqlite3.Connection) -> dict:
    """算出该课程当前的上传配额明细。

    既用于上传时的超限判定，也用于上传前在界面上展示剩余空间，所以把四个上限
    （单文件大小、课程总量、站点总量、磁盘剩余空间）全部算出来，取最紧的一条
    作为本次允许的最大字节数——这样流式写入时只需比较一次，超限原因也准确。
    """

    settings = get_settings()
    # 只统计未删除的资料。回收站里的资料虽然还占着磁盘，但用户已经把它当成删掉了，
    # 若继续算进配额，就会出现「删了文件却还是传不上新的」这种反直觉结果；
    # 真正的物理兜底是下面那条磁盘剩余空间检查。
    used_total = db.execute(
        "SELECT COALESCE(SUM(size), 0) FROM files WHERE deleted_at IS NULL"
    ).fetchone()[0]
    used_course = db.execute(
        "SELECT COALESCE(SUM(size), 0) FROM files "
        "WHERE course_id = ? AND deleted_at IS NULL",
        (course_id,),
    ).fetchone()[0]
    candidates = [
        (
            settings.max_file_size,
            f"文件不能超过 {format_bytes(settings.max_file_size)}",
        )
    ]
    if settings.max_total_bytes:
        candidates.append(
            (
                settings.max_total_bytes - used_total,
                f"站点资料总量已达上限 {format_bytes(settings.max_total_bytes)}，"
                "请先清理旧资料",
            )
        )
    if settings.max_course_bytes:
        candidates.append(
            (
                settings.max_course_bytes - used_course,
                f"该课程资料总量已达上限 {format_bytes(settings.max_course_bytes)}，"
                "请先清理旧资料",
            )
        )
    disk_free: int | None = None
    try:
        upload_root = uploads_path()
        # 上传目录可能还没建，退到项目根目录探测同一个磁盘。
        target = upload_root if upload_root.exists() else PROJECT_ROOT
        disk_free = shutil.disk_usage(target).free
        candidates.append(
            (disk_free - settings.min_free_space, "服务器磁盘空间不足，暂时无法上传")
        )
    except OSError as error:
        # 探测失败时放行，避免因为统计不到磁盘而完全无法上传。
        logger.warning(
            "disk space probe failed: %s",
            error,
            extra={"event": "disk_check"},
        )
    allowed, reason = min(candidates, key=lambda item: item[0])
    return {
        "course_id": course_id,
        "allowed_bytes": max(0, allowed),
        "reason": reason,
        "max_file_size": settings.max_file_size,
        "course_limit": settings.max_course_bytes or None,
        "course_used": used_course,
        "course_remaining": (
            max(0, settings.max_course_bytes - used_course)
            if settings.max_course_bytes
            else None
        ),
        "site_limit": settings.max_total_bytes or None,
        "site_used": used_total,
        "site_remaining": (
            max(0, settings.max_total_bytes - used_total)
            if settings.max_total_bytes
            else None
        ),
        "disk_free": disk_free,
    }


def upload_allowance(course_id: int, db: sqlite3.Connection) -> tuple[int, str]:
    """上传时只关心最紧的那条上限，复用 upload_quota 的结果。"""

    quota = upload_quota(course_id, db)
    return quota["allowed_bytes"], quota["reason"]


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


def stored_file_path(filename: str) -> Path | None:
    root = uploads_path().resolve()
    path = (root / filename).resolve()
    return path if root in path.parents else None


def fts_phrase(term: str) -> str:
    """trigram 分词器下用双引号包住词条即可做任意位置的子串匹配。"""

    return '"{}"'.format(term.replace('"', ""))


def build_search_filter(
    keyword: str, use_fts: bool
) -> tuple[str, list[object]]:
    """按空格拆词生成过滤条件：长词走 FTS 索引，短词回退 LIKE，词条之间是 AND。

    trigram 分词器只索引长度不小于 3 的片段，短词无法命中，必须交给 LIKE。
    """

    clauses: list[str] = []
    params: list[object] = []
    for term in keyword.split():
        if use_fts and len(term) >= MIN_FTS_TERM_LENGTH:
            clauses.append(
                "(f.id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH ?)"
                " OR f.course_id IN"
                " (SELECT id FROM courses WHERE name LIKE ? ESCAPE '\\'))"
            )
            params.extend([fts_phrase(term), f"%{escape_like(term)}%"])
        else:
            clauses.append(
                "(LOWER(f.title) LIKE LOWER(?) ESCAPE '\\'"
                " OR LOWER(f.original_name) LIKE LOWER(?) ESCAPE '\\'"
                " OR LOWER(c.name) LIKE LOWER(?) ESCAPE '\\')"
            )
            params.extend([f"%{escape_like(term)}%"] * 3)
    if not clauses:
        return "", []
    return " AND ".join(clauses), params


SortOption = Literal[
    "newest", "oldest", "name", "size", "最新", "最早", "标题", "大小"
]
SORT_OPTIONS: dict[str, str] = {
    "newest": "f.upload_time DESC, f.id DESC",
    "oldest": "f.upload_time ASC, f.id ASC",
    "name": "f.title COLLATE NOCASE ASC, f.id DESC",
    "size": "f.size DESC, f.id DESC",
}
# 中文别名归一化到白名单键；排序片段始终取自 SORT_OPTIONS，不拼接用户输入。
SORT_ALIASES: dict[str, str] = {
    "最新": "newest",
    "最早": "oldest",
    "标题": "name",
    "大小": "size",
}


def build_extra_filters(
    course_id: int | None,
    extension: str | None,
    start: date | None,
    end: date | None,
) -> tuple[list[str], list[object]]:
    """课程、扩展名、上传时间范围三类筛选条件，与关键词条件是 AND 关系。"""

    clauses: list[str] = []
    params: list[object] = []
    if course_id is not None:
        clauses.append("f.course_id = ?")
        params.append(course_id)
    if extension:
        clauses.append("LOWER(f.original_name) LIKE ? ESCAPE '\\'")
        params.append(f"%.{escape_like(extension)}")
    if start is not None:
        clauses.append("f.upload_time >= ?")
        params.append(f"{start.isoformat()} 00:00:00")
    if end is not None:
        clauses.append("f.upload_time <= ?")
        params.append(f"{end.isoformat()} 23:59:59")
    return clauses, params


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


def file_visibility(user: sqlite3.Row | None) -> tuple[str, list[object]]:
    """当前用户能看到的资料范围，返回 SQL 片段与对应参数。

    片段只由内部常量拼成，不含任何用户输入。管理员看全部、上传者额外看到自己
    待审核的资料、其他人和访客只看已通过的。已删除（在回收站）的资料对所有人
    都不再可见，要看去回收站面板。
    """

    clause = "f.status = 'approved'"
    params: list[object] = []
    if user is not None and user["role"] == "admin":
        clause = "1 = 1"
    elif user is not None and user["role"] == "uploader":
        clause = "(f.status = 'approved' OR f.uploaded_by = ?)"
        params.append(user["id"])
    return f"({clause}) AND f.deleted_at IS NULL", params


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

    visibility, visibility_params = file_visibility(user)
    params: list[object] = [course_id, *visibility_params]
    total = db.execute(
        f"SELECT COUNT(*) FROM files AS f WHERE f.course_id = ? AND {visibility}",  # noqa: S608 - 可见性片段来自内部常量
        params,
    ).fetchone()[0]
    params.extend([page_size, (page - 1) * page_size])
    rows = db.execute(
        f"""
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files AS f WHERE f.course_id = ? AND {visibility}
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 可见性片段来自内部常量
        params,
    ).fetchall()
    return FilePage(
        **page_response([file_response(row) for row in rows], total, page, page_size)
    )


@router.get("/api/courses/{course_id}/quota", include_in_schema=False)
@router.get(
    "/接口/课程/{course_id}/配额",
    response_model=CourseQuota,
    summary="查看课程上传配额",
    operation_id="查看课程上传配额",
)
def course_quota(
    course_id: int,
    user: sqlite3.Row = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> CourseQuota:
    if not course_exists(course_id, db):
        raise HTTPException(status_code=404, detail="课程不存在")
    return CourseQuota(**upload_quota(course_id, db))


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

        allowance, limit_reason = upload_allowance(course_id, db)
        if allowance <= 0:
            raise HTTPException(status_code=413, detail=limit_reason)
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
                if size > allowance:
                    raise HTTPException(status_code=413, detail=limit_reason)
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
        "SELECT uploaded_by FROM files WHERE id = ? AND deleted_at IS NULL", (file_id,)
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if user["role"] != "admin" and existing["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="没有编辑此资料的权限")
    cursor = db.execute(
        "UPDATE files SET title = ? WHERE id = ? AND deleted_at IS NULL",
        (update.title, file_id),
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
    """删除资料 —— 只移入回收站（软删除），磁盘文件先保留。

    误删是真实会发生的操作，而以前这里是直接物理删除、删了就找不回来。现在改为
    打标记，回收站保留一段时间（默认 30 天，见 trash_retention_days），期间可以
    恢复，超期由维护任务真正清理。
    """

    row = db.execute(
        "SELECT original_name, uploaded_by FROM files "
        "WHERE id = ? AND deleted_at IS NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if user["role"] != "admin" and row["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="没有删除此资料的权限")
    cursor = db.execute(
        """
        UPDATE files SET deleted_at = CURRENT_TIMESTAMP, deleted_by = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (user["id"], file_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="资料不存在")
    record_audit(
        db,
        user["id"],
        "delete",
        "file",
        file_id,
        f"移入回收站：{row['original_name']}",
    )
    db.commit()


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
        FROM files WHERE id = ? AND deleted_at IS NULL
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


# 只允许确定无法执行脚本的类型内联预览；媒体类型按扩展名推导，
# 不能使用上传时客户端声明的 mime_type。
PREVIEW_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


@download_router.get("/api/files/{file_id}/preview", include_in_schema=False)
@download_router.get(
    "/接口/资料/{file_id}/预览",
    summary="在线预览资料",
    operation_id="在线预览资料",
)
def preview_file(
    file_id: int,
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        "SELECT filename, original_name, status, uploaded_by FROM files "
        "WHERE id = ? AND deleted_at IS NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if row["status"] != "approved":
        if user is None or (user["role"] != "admin" and user["id"] != row["uploaded_by"]):
            raise HTTPException(status_code=404, detail="资料不存在")

    media_type = PREVIEW_MEDIA_TYPES.get(Path(row["original_name"]).suffix.lower())
    if media_type is None:
        raise HTTPException(status_code=415, detail="该文件类型不支持在线预览")
    path = stored_file_path(row["filename"])
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    headers = {
        # 强制浏览器按我们声明的类型解析，避免上传内容被当成 HTML 执行。
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "private, max-age=300",
    }
    if media_type.startswith("text/"):
        headers["Content-Security-Policy"] = "default-src 'none'"
    record_audit(db, user["id"] if user else None, "preview", "file", file_id)
    db.commit()
    return FileResponse(
        path,
        media_type=media_type,
        filename=row["original_name"],
        content_disposition_type="inline",
        headers=headers,
    )


# 一次打包的资料数量上限。SQLite 对单条语句的占位符数量有上限，课程资料量本来
# 就小，给一个明确的上限比让用户撞到数据库报错更好。
MAX_ARCHIVE_FILES = 300


def unique_archive_name(name: str, used: set[str]) -> str:
    """zip 内条目名去重：重名时在扩展名前插入 (1)、(2)……"""

    if name.lower() not in used:
        used.add(name.lower())
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 1
    while True:
        candidate = f"{stem}({index}){suffix}"
        if candidate.lower() not in used:
            used.add(candidate.lower())
            return candidate
        index += 1


def archive_filename(course_name: str) -> str:
    """把课程名整理成安全的 zip 文件名。"""

    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", course_name).strip(" .")
    return f"{cleaned or '课程资料'}.zip"


@download_router.get("/api/courses/{course_id}/archive", include_in_schema=False)
@download_router.get(
    "/接口/课程/{course_id}/打包下载",
    summary="打包下载课程资料",
    operation_id="打包下载课程资料",
)
def download_course_archive(
    course_id: int,
    资料编号: list[int] | None = Query(
        None, description="要打包的资料编号，可重复传多次；不传表示整门课"
    ),
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """把选中的资料（不传编号则整门课）打成一个 zip 下发。

    压缩包先写到磁盘上的临时文件再发送，避免大课程把整个包堆在内存里；下载结束
    后由后台任务删掉临时文件。可见性与课程资料列表保持一致，所以待审核、已拒绝
    或已进回收站的资料不会被打包。
    """

    if not course_exists(course_id, db):
        raise HTTPException(status_code=404, detail="课程不存在")

    visibility, params = file_visibility(user)
    conditions = [visibility]
    if 资料编号:
        selected = list(dict.fromkeys(资料编号))
        if len(selected) > MAX_ARCHIVE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"一次最多打包 {MAX_ARCHIVE_FILES} 份资料",
            )
        placeholders = ", ".join("?" for _ in selected)
        conditions.append(f"f.id IN ({placeholders})")
        params.extend(selected)
    rows = db.execute(
        f"""
        SELECT f.id, f.filename, f.original_name
        FROM files AS f
        WHERE f.course_id = ? AND {' AND '.join(conditions)}
        ORDER BY f.id
        """,  # noqa: S608 - 条件由内部函数与占位符生成
        [course_id, *params],
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="没有可打包的资料")

    archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    archive_path = Path(archive.name)
    archive.close()
    used: set[str] = set()
    packed = 0
    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for row in rows:
                path = stored_file_path(row["filename"])
                if path is None or not path.is_file():
                    # 数据库有记录但磁盘文件缺失：跳过这一份，而不是让整包失败。
                    continue
                bundle.write(path, unique_archive_name(row["original_name"], used))
                packed += 1
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    if not packed:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="资料文件已丢失，无法打包")

    course = db.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
    record_audit(
        db,
        user["id"] if user else None,
        "download",
        "course",
        course_id,
        f"打包下载 {packed} 份资料",
    )
    db.commit()
    return FileResponse(
        archive_path,
        filename=archive_filename(course["name"] if course else ""),
        media_type="application/zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.get("/api/my-files", include_in_schema=False)
@router.get(
    "/接口/我的资料",
    response_model=FilePage,
    summary="查看我的上传",
    operation_id="查看我的上传",
)
def list_my_files(
    状态: Literal["pending", "approved", "rejected"] | None = Query(
        None, description="按审核状态筛选"
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> FilePage:
    conditions = ["f.uploaded_by = ?", "f.deleted_at IS NULL"]
    params: list[object] = [user["id"]]
    if 状态 is not None:
        conditions.append("f.status = ?")
        params.append(状态)
    where = " AND ".join(conditions)

    total = db.execute(
        f"SELECT COUNT(*) FROM files AS f WHERE {where}",  # noqa: S608 - 条件由内部白名单拼接
        params,
    ).fetchone()[0]
    rows = db.execute(
        f"""
        SELECT f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
               f.mime_type, f.sha256, f.status, f.uploaded_by,
               c.name AS course_name, c.college, c.semester, f.filename
        FROM files AS f JOIN courses AS c ON c.id = f.course_id
        WHERE {where}
        ORDER BY f.id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return FilePage(
        **page_response([search_response(row) for row in rows], total, page, page_size)
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
    课程编号: int | None = Query(None, ge=1, description="按课程编号筛选"),
    类型: str | None = Query(None, max_length=20, description="按扩展名筛选，如 pdf"),
    起始时间: str | None = Query(None, description="上传时间不早于该日期（YYYY-MM-DD）"),
    结束时间: str | None = Query(None, description="上传时间不晚于该日期（YYYY-MM-DD）"),
    排序: SortOption = Query(
        "newest",
        description="排序方式：newest/oldest/name/size，也接受中文 最新/最早/标题/大小",
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: sqlite3.Connection = Depends(get_db),
) -> FilePage:
    keyword = (关键词 or request.query_params.get("q", "")).strip()
    extension = (类型 or "").strip().lstrip(".").lower()
    start = parse_date(起始时间, "起始时间")
    end = parse_date(结束时间, "结束时间")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="起始时间不能晚于结束时间")

    extra_clauses, extra_params = build_extra_filters(课程编号, extension, start, end)
    # 关键词和筛选条件都为空时不必查库；只有筛选条件时按条件列出资料。
    if not keyword and not extra_clauses:
        return FilePage(**page_response([], 0, page, page_size))

    order = SORT_OPTIONS[SORT_ALIASES.get(排序, 排序)]
    total = 0
    rows: list[sqlite3.Row] = []
    for use_fts in ((True, False) if keyword else (False,)):
        keyword_clause, keyword_params = build_search_filter(keyword, use_fts)
        conditions = [
            clause for clause in (keyword_clause, *extra_clauses) if clause
        ]
        clause = " AND ".join(conditions) if conditions else "1 = 1"
        params: list[object] = [*keyword_params, *extra_params]
        try:
            total = db.execute(
                "SELECT COUNT(*) FROM files AS f "  # noqa: S608 - 条件由内部函数生成
                "JOIN courses AS c ON c.id = f.course_id "
                f"WHERE f.status = 'approved' AND f.deleted_at IS NULL AND ({clause})",
                params,
            ).fetchone()[0]
            rows = db.execute(
                f"""
                SELECT f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
                       f.mime_type, f.sha256, f.status,
                       c.name AS course_name, c.college, c.semester, f.filename
                FROM files AS f JOIN courses AS c ON c.id = f.course_id
                WHERE f.status = 'approved' AND f.deleted_at IS NULL AND ({clause})
                ORDER BY {order} LIMIT ? OFFSET ?
                """,  # noqa: S608 - 条件与排序都来自内部白名单
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
            break
        except sqlite3.OperationalError:
            # 运行环境没有 FTS5 或索引损坏时退回纯 LIKE 搜索。
            if not use_fts:
                raise
    return FilePage(
        **page_response([search_response(row) for row in rows], total, page, page_size)
    )


REVIEW_LABELS = {"approved": "已通过", "rejected": "已拒绝"}


def apply_file_review(
    file_id: int,
    status_value: str,
    actor: sqlite3.Row,
    db: sqlite3.Connection,
) -> dict:
    """单份资料的审核逻辑。批量接口复用它，保证审计与校验完全一致。"""

    cursor = db.execute(
        "UPDATE files SET status = ? WHERE id = ? AND deleted_at IS NULL",
        (status_value, file_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="资料不存在")
    record_audit(
        db,
        actor["id"],
        status_value,
        "file",
        file_id,
        f"资料审核结果：{status_value}",
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
    return apply_file_review(file_id, review.status, user, db)


@router.post(
    "/api/files/batch/review",
    include_in_schema=False,
)
# 批量审核故意用 POST：路由按注册顺序匹配，写成 PATCH 的话
# /接口/资料/批量审核 会先被 PATCH /接口/资料/{资料编号} 吃掉，
# 「批量审核」当编号解析失败就变成 422。这个前缀下没有别的 POST，用 POST 不会撞。
@router.post(
    "/接口/资料/批量审核",
    response_model=BatchResult,
    summary="批量通过或拒绝资料",
    operation_id="批量审核资料",
)
def batch_review_files(
    payload: FileBatchReview,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> BatchResult:
    results: list[BatchItemResult] = []
    # dict.fromkeys 去重同时保持传入顺序，避免同一个编号被审两遍。
    for file_id in dict.fromkeys(payload.ids):
        try:
            apply_file_review(file_id, payload.status, user, db)
        except HTTPException as error:
            # 逐条独立成败：某一份不存在或已被删除，不影响其余几份。
            db.rollback()
            results.append(
                BatchItemResult(id=file_id, ok=False, message=str(error.detail))
            )
        else:
            results.append(
                BatchItemResult(
                    id=file_id, ok=True, message=REVIEW_LABELS[payload.status]
                )
            )
    return BatchResult.from_items(results)


trash_router = APIRouter(tags=["回收站"])

TRASH_COLUMNS = """
    f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
    f.status, f.deleted_at, f.filename,
    c.name AS course_name,
    d.username AS deleted_by_name
"""


def trash_response(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "course_name": row["course_name"],
        "title": row["title"],
        "original_name": row["original_name"],
        "size": row["size"],
        "upload_time": row["upload_time"],
        "status": row["status"],
        "deleted_at": row["deleted_at"],
        "deleted_by_name": row["deleted_by_name"],
    }


@trash_router.get("/api/trash", include_in_schema=False)
@trash_router.get(
    "/接口/回收站",
    response_model=TrashFilePage,
    summary="查看回收站",
    operation_id="查看回收站",
)
def list_trash(
    关键词: str = Query("", max_length=80, description="按标题、文件名、课程或删除人筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> TrashFilePage:
    conditions = ["f.deleted_at IS NOT NULL"]
    params: list[object] = []
    keyword = 关键词.strip()
    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        conditions.append(
            "(f.title LIKE ? ESCAPE '\\' OR f.original_name LIKE ? ESCAPE '\\'"
            " OR c.name LIKE ? ESCAPE '\\' OR d.username LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern] * 4)
    where = " AND ".join(conditions)
    # 课程或删除人可能已经不存在（课程被删、用户被删），所以两个都用 LEFT JOIN。
    joins = (
        "LEFT JOIN courses AS c ON c.id = f.course_id "
        "LEFT JOIN users AS d ON d.id = f.deleted_by"
    )
    total = db.execute(
        f"SELECT COUNT(*) FROM files AS f {joins} WHERE {where}",  # noqa: S608 - 条件由内部白名单拼接
        params,
    ).fetchone()[0]
    rows = db.execute(
        f"""
        SELECT {TRASH_COLUMNS}
        FROM files AS f {joins} WHERE {where}
        ORDER BY f.deleted_at DESC, f.id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return TrashFilePage(
        **page_response([trash_response(row) for row in rows], total, page, page_size)
    )


@trash_router.post(
    "/api/trash/{file_id}/restore",
    include_in_schema=False,
)
@trash_router.post(
    "/接口/回收站/{file_id}/恢复",
    response_model=dict,
    summary="恢复回收站资料",
    operation_id="恢复回收站资料",
)
def restore_trashed_file(
    file_id: int,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    row = db.execute(
        "SELECT course_id, original_name FROM files "
        "WHERE id = ? AND deleted_at IS NOT NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="回收站里没有这条资料")
    try:
        db.execute(
            "UPDATE files SET deleted_at = NULL, deleted_by = NULL WHERE id = ?",
            (file_id,),
        )
        record_audit(
            db,
            user["id"],
            "restore",
            "file",
            file_id,
            f"从回收站恢复：{row['original_name']}",
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        # 内容去重索引在「同课程 + 同 sha256 + 未删除」上唯一。恢复时若这门课已经有
        # 一份内容相同的资料，就会撞上它，此时应提示用户而不是报 500。
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="该课程已存在内容相同的资料，无法恢复",
        ) from error
    restored = db.execute(
        """
        SELECT id, course_id, title, original_name, size, upload_time,
               mime_type, sha256, status, uploaded_by
        FROM files WHERE id = ?
        """,
        (file_id,),
    ).fetchone()
    return file_response(restored)


@trash_router.delete(
    "/api/trash/{file_id}",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@trash_router.delete(
    "/接口/回收站/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="彻底删除回收站资料",
    operation_id="彻底删除回收站资料",
)
def purge_trashed_file(
    file_id: int,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute(
        "SELECT filename, original_name FROM files "
        "WHERE id = ? AND deleted_at IS NOT NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="回收站里没有这条资料")
    # 与删除课程走同一套暂存机制：先把文件改名移开，数据库删除提交成功后才真正
    # unlink；中途失败会回滚并把文件改回来。
    staged = stage_stored_files([row], db)
    try:
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        record_audit(
            db,
            user["id"],
            "purge",
            "file",
            file_id,
            f"彻底删除：{row['original_name']}",
        )
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_files(staged, db)
        raise
    discard_staged_files(staged, db)
