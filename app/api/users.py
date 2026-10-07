import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import public_user, require_roles
from app.auth import hash_password
from app.db import get_db, record_audit
from app.schemas import (
    PasswordReset,
    User,
    UserAdmin,
    UserCreate,
    UserPage,
    UserUpdate,
)

router = APIRouter(tags=["账户"])

Role = Literal["admin", "uploader", "viewer"]
ROLE_LABELS = {"admin": "管理员", "uploader": "上传者", "viewer": "浏览者"}

USER_COLUMNS = """
    u.id, u.username, u.role, u.is_active, u.created_at,
    (SELECT COUNT(*) FROM files AS f
     WHERE f.uploaded_by = u.id AND f.deleted_at IS NULL) AS upload_count
"""


def user_admin_response(row: sqlite3.Row) -> UserAdmin:
    return UserAdmin(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        upload_count=row["upload_count"],
    )


def fetch_user(user_id: int, db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute(
        f"SELECT {USER_COLUMNS} FROM users AS u WHERE u.id = ?",  # noqa: S608 - 列名来自内部常量
        (user_id,),
    ).fetchone()


def count_active_admins(db: sqlite3.Connection) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
    ).fetchone()[0]


@router.get("/api/users", include_in_schema=False)
@router.get(
    "/接口/用户",
    response_model=UserPage,
    summary="查看用户列表",
    operation_id="查看用户列表",
)
def list_users(
    关键词: str = Query("", max_length=80, description="按用户名筛选"),
    角色: Role | None = Query(None, description="按角色筛选"),
    启用: bool | None = Query(None, description="按启用状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> UserPage:
    conditions: list[str] = []
    params: list[object] = []
    keyword = 关键词.strip()
    if keyword:
        conditions.append("u.username LIKE ? ESCAPE '\\'")
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
    if 角色 is not None:
        conditions.append("u.role = ?")
        params.append(角色)
    if 启用 is not None:
        conditions.append("u.is_active = ?")
        params.append(1 if 启用 else 0)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM users AS u {where}",  # noqa: S608 - 条件由内部白名单拼接
        params,
    ).fetchone()[0]
    rows = db.execute(
        f"""
        SELECT {USER_COLUMNS}
        FROM users AS u {where}
        ORDER BY u.id ASC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return UserPage(
        items=[user_admin_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "/api/users",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/接口/用户",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="管理员创建用户",
    operation_id="管理员创建用户",
)
def create_user(
    request: UserCreate,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> User:
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (request.username, request.password_hash(), request.role),
        )
        record_audit(
            db,
            user["id"],
            "create",
            "user",
            cursor.lastrowid,
            f"创建用户 {request.username}",
        )
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        if "username" in str(error).lower():
            raise HTTPException(status_code=409, detail="用户名已存在") from error
        raise
    row = db.execute(
        "SELECT id, username, role FROM users WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return public_user(row)


@router.patch(
    "/api/users/{user_id}",
    include_in_schema=False,
)
@router.patch(
    "/接口/用户/{user_id}",
    response_model=UserAdmin,
    summary="修改用户角色或启用状态",
    operation_id="修改用户角色或启用状态",
)
def update_user(
    user_id: int,
    update: UserUpdate,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> UserAdmin:
    row = fetch_user(user_id, db)
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    old_role = row["role"]
    was_active = bool(row["is_active"])
    new_role: str = update.role if update.role is not None else old_role
    new_active = update.is_active if update.is_active is not None else was_active

    if user_id == user["id"]:
        if new_role != old_role:
            raise HTTPException(status_code=409, detail="不能修改自己的角色")
        if not new_active:
            raise HTTPException(status_code=409, detail="不能停用当前登录的账户")

    if old_role == "admin" and was_active and not (new_role == "admin" and new_active):
        if count_active_admins(db) <= 1:
            raise HTTPException(status_code=409, detail="系统必须保留至少一个启用的管理员")

    if new_role == old_role and new_active == was_active:
        return user_admin_response(row)

    db.execute(
        "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
        (new_role, 1 if new_active else 0, user_id),
    )
    changes: list[str] = []
    if new_role != old_role:
        old_label = ROLE_LABELS.get(old_role, old_role)
        new_label = ROLE_LABELS.get(new_role, new_role)
        changes.append(f"角色 {old_label} → {new_label}")
    if new_active != was_active:
        changes.append("状态 启用 → 停用" if not new_active else "状态 停用 → 启用")
    record_audit(
        db,
        user["id"],
        "update",
        "user",
        user_id,
        f"修改用户 {row['username']}：{'，'.join(changes)}",
    )
    if not new_active:
        # 停用后立即失效其会话，避免已登录的旧令牌继续访问。
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()
    updated = fetch_user(user_id, db)
    return user_admin_response(updated)


@router.post(
    "/api/users/{user_id}/password",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.post(
    "/接口/用户/{user_id}/重置密码",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="重置用户密码",
    operation_id="重置用户密码",
)
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(payload.password), user_id),
    )
    # 旧密码对应的会话全部作废，管理员重置后对方必须重新登录。
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    record_audit(
        db,
        user["id"],
        "reset_password",
        "user",
        user_id,
        f"重置用户 {row['username']} 的密码",
    )
    db.commit()
