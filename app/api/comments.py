"""资料评论。

登录后可发评论，作者与管理员可删；匿名可读已通过资料的评论。前端用轮询刷新（非实时）。
评论一律当纯文本处理，不做任何 HTML 解析。
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import current_user, optional_user
from app.api.common import page_response
from app.db import get_db, record_audit
from app.schemas import Comment, CommentCreate, CommentPage

router = APIRouter(tags=["评论"])

COMMENT_COLUMNS = """
    c.id, c.file_id, c.user_id, c.body, c.created_at, u.username AS username
"""


def comment_response(row: sqlite3.Row) -> Comment:
    return Comment(
        id=row["id"],
        file_id=row["file_id"],
        user_id=row["user_id"],
        username=row["username"],
        body=row["body"],
        created_at=row["created_at"],
    )


def ensure_commentable_file(
    file_id: int, user: sqlite3.Row | None, db: sqlite3.Connection
) -> None:
    """评论的可见性跟资料一致：待审/已拒绝的资料对非本人不可见，评论也一并隐藏。"""

    row = db.execute(
        "SELECT status, uploaded_by FROM files WHERE id = ? AND deleted_at IS NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if row["status"] != "approved":
        if user is None or (user["role"] != "admin" and user["id"] != row["uploaded_by"]):
            raise HTTPException(status_code=404, detail="资料不存在")


@router.get("/api/files/{file_id}/comments", include_in_schema=False)
@router.get(
    "/接口/资料/{file_id}/评论",
    response_model=CommentPage,
    summary="查看评论",
    operation_id="查看评论",
)
def list_comments(
    file_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
) -> CommentPage:
    ensure_commentable_file(file_id, user, db)
    total = db.execute(
        "SELECT COUNT(*) FROM comments WHERE file_id = ?", (file_id,)
    ).fetchone()[0]
    rows = db.execute(
        f"""
        SELECT {COMMENT_COLUMNS}
        FROM comments AS c JOIN users AS u ON u.id = c.user_id
        WHERE c.file_id = ?
        ORDER BY c.id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 列名来自内部常量
        (file_id, page_size, (page - 1) * page_size),
    ).fetchall()
    return CommentPage(
        **page_response([comment_response(row) for row in rows], total, page, page_size)
    )


@router.post(
    "/api/files/{file_id}/comments",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/接口/资料/{file_id}/评论",
    response_model=Comment,
    status_code=status.HTTP_201_CREATED,
    summary="发表评论",
    operation_id="发表评论",
)
def create_comment(
    file_id: int,
    payload: CommentCreate,
    user: sqlite3.Row = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> Comment:
    ensure_commentable_file(file_id, user, db)
    cursor = db.execute(
        "INSERT INTO comments (file_id, user_id, body) VALUES (?, ?, ?)",
        (file_id, user["id"], payload.body),
    )
    record_audit(db, user["id"], "comment", "file", file_id, "发表评论")
    db.commit()
    row = db.execute(
        f"""
        SELECT {COMMENT_COLUMNS}
        FROM comments AS c JOIN users AS u ON u.id = c.user_id
        WHERE c.id = ?
        """,  # noqa: S608 - 列名来自内部常量
        (cursor.lastrowid,),
    ).fetchone()
    return comment_response(row)


@router.delete(
    "/api/comments/{comment_id}",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/接口/评论/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除评论",
    operation_id="删除评论",
)
def delete_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute(
        "SELECT user_id, file_id FROM comments WHERE id = ?", (comment_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    if user["role"] != "admin" and row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="没有删除此评论的权限")
    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    record_audit(db, user["id"], "delete", "file", row["file_id"], "删除评论")
    db.commit()
