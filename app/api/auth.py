import sqlite3

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.auth import (
    SESSION_COOKIE,
    new_session_token,
    session_token_hash,
    verify_password,
)
from app.config import get_settings
from app.db import (
    clear_login_failures,
    get_db,
    login_lock_remaining,
    record_audit,
    register_login_failure,
)
from app.schemas import LoginRequest, User, UserCreate

router = APIRouter(tags=["账户"])


def public_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], username=row["username"], role=row["role"])


def find_session_user(
    session_cookie: str | None, db: sqlite3.Connection
) -> sqlite3.Row | None:
    if not session_cookie:
        return None
    row = db.execute(
        """
        SELECT u.id, u.username, u.role
        FROM sessions AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires_at > CURRENT_TIMESTAMP
        """,
        (session_token_hash(session_cookie),),
    ).fetchone()
    if row is None:
        db.execute("DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP")
        db.commit()
    return row


def current_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    row = find_session_user(session_cookie, db)
    if row is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return row


def optional_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row | None:
    return find_session_user(session_cookie, db)


def require_roles(*roles: str):
    def dependency(user: sqlite3.Row = Depends(current_user)) -> sqlite3.Row:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="没有执行此操作的权限")
        return user

    return dependency


@router.post(
    "/api/login",
    include_in_schema=False,
)
@router.post(
    "/接口/登录",
    response_model=User,
    summary="登录",
    operation_id="登录",
)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
) -> User:
    settings = get_settings()
    # 反向代理后面拿到的可能是代理地址，但登录键同时包含用户名，按账号锁定仍然有效。
    client_ip = request.client.host if request.client else "unknown"
    username = credentials.username

    remaining = login_lock_remaining(db, username, client_ip)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请在 {remaining} 秒后重试",
        )

    row = db.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not verify_password(credentials.password, row["password_hash"]):
        failed = register_login_failure(
            db,
            username,
            client_ip,
            settings.login_max_attempts,
            settings.login_lockout_seconds,
        )
        if failed >= settings.login_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "登录失败次数过多，账户已被临时锁定"
                    f" {settings.login_lockout_seconds} 秒"
                ),
            )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    clear_login_failures(db, username, client_ip)
    token, token_hash, expires_at = new_session_token()
    db.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (row["id"], token_hash, expires_at),
    )
    record_audit(db, row["id"], "login", "user", row["id"], "用户登录")
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return User(id=row["id"], username=row["username"], role=row["role"])


@router.get(
    "/api/me",
    include_in_schema=False,
)
@router.get(
    "/接口/当前用户",
    response_model=User,
    summary="查看当前用户",
    operation_id="查看当前用户",
)
def get_me(user: sqlite3.Row = Depends(current_user)) -> User:
    return public_user(user)


@router.post(
    "/api/logout",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.post(
    "/接口/退出",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="退出登录",
    operation_id="退出登录",
)
def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: sqlite3.Row | None = Depends(optional_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    if session_cookie:
        db.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (session_token_hash(session_cookie),),
        )
    if user is not None:
        record_audit(db, user["id"], "logout", "user", user["id"], "用户退出登录")
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


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
