"""只读分享链接（便捷链接）。

给管理员为某门课生成一条带有效期的链接。分享页只展示该课程「已通过」的资料并给出下载入口。
注意：本站的课程浏览与已通过资料下载本来就是公开的，所以这里的有效期与撤销只作用于
「分享页」，并不能锁住资料字节本身——详见 README「已知局限」。
"""

import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_roles
from app.db import get_db, record_audit
from app.schemas import Course, ShareCreate, ShareLink, ShareView

router = APIRouter(tags=["分享"])

FILE_COLUMNS = (
    "id, title, original_name, size, upload_time, mime_type, sha256, status, version"
)


def share_link_response(row: sqlite3.Row) -> ShareLink:
    return ShareLink(
        id=row["id"],
        token=row["token"],
        url=f"/分享/{row['token']}",
        note=row["note"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


@router.get("/api/courses/{course_id}/share", include_in_schema=False)
@router.get(
    "/接口/课程/{course_id}/分享",
    response_model=list[ShareLink],
    summary="查看课程的分享链接",
    operation_id="查看课程的分享链接",
)
def list_share_links(
    course_id: int,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> list[ShareLink]:
    if db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    rows = db.execute(
        "SELECT id, token, note, created_at, expires_at FROM share_links "
        "WHERE course_id = ? ORDER BY id DESC",
        (course_id,),
    ).fetchall()
    return [share_link_response(row) for row in rows]


@router.post(
    "/api/courses/{course_id}/share",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/接口/课程/{course_id}/分享",
    response_model=ShareLink,
    status_code=status.HTTP_201_CREATED,
    summary="创建课程分享链接",
    operation_id="创建课程分享链接",
)
def create_share_link(
    course_id: int,
    payload: ShareCreate,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> ShareLink:
    if db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    token = secrets.token_urlsafe(24)
    cursor = db.execute(
        "INSERT INTO share_links (token, course_id, created_by, note, expires_at) "
        "VALUES (?, ?, ?, ?, datetime('now', ?))",
        (token, course_id, user["id"], payload.note, f"+{payload.days} days"),
    )
    record_audit(
        db,
        user["id"],
        "create",
        "course",
        course_id,
        f"创建分享链接（{payload.days} 天）",
    )
    db.commit()
    row = db.execute(
        "SELECT id, token, note, created_at, expires_at FROM share_links WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return share_link_response(row)


@router.delete(
    "/api/shares/{share_id}",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/接口/分享/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="撤销分享链接",
    operation_id="撤销分享链接",
)
def revoke_share_link(
    share_id: int,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute(
        "SELECT course_id FROM share_links WHERE id = ?", (share_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="分享链接不存在")
    db.execute("DELETE FROM share_links WHERE id = ?", (share_id,))
    record_audit(db, user["id"], "delete", "course", row["course_id"], "撤销分享链接")
    db.commit()


@router.get("/api/shares/{token}", include_in_schema=False)
@router.get(
    "/接口/分享/{token}",
    response_model=ShareView,
    summary="查看分享内容",
    operation_id="查看分享内容",
)
def view_share(token: str, db: sqlite3.Connection = Depends(get_db)) -> ShareView:
    row = db.execute(
        "SELECT course_id, note, expires_at, "
        "(expires_at <= CURRENT_TIMESTAMP) AS expired "
        "FROM share_links WHERE token = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="分享链接不存在或已撤销")
    if row["expired"]:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="分享链接已过期")

    course_row = db.execute(
        "SELECT id, name, college, semester, version, tags FROM courses WHERE id = ?",
        (row["course_id"],),
    ).fetchone()
    if course_row is None:
        raise HTTPException(status_code=404, detail="课程不存在")

    file_rows = db.execute(
        f"SELECT {FILE_COLUMNS} FROM files "  # noqa: S608 - 列名来自内部常量
        "WHERE course_id = ? AND status = 'approved' AND deleted_at IS NULL "
        "ORDER BY id DESC",
        (row["course_id"],),
    ).fetchall()
    files = [
        {
            "id": file_row["id"],
            "title": file_row["title"],
            "original_name": file_row["original_name"],
            "size": file_row["size"],
            "upload_time": file_row["upload_time"],
            "mime_type": file_row["mime_type"],
        }
        for file_row in file_rows
    ]
    return ShareView(
        course=Course(**dict(course_row)),
        files=files,
        note=row["note"],
        expires_at=row["expires_at"],
    )
