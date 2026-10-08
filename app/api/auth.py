import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    hash_password,
    new_session_token,
    session_expiry,
    session_hard_deadline,
    session_needs_renewal,
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
from app.schemas import LoginRequest, PasswordChange, User

router = APIRouter(tags=["账户"])


def public_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], username=row["username"], role=row["role"])


def set_session_cookie(response: Response, token: str) -> None:
    """写会话 Cookie。登录和滑动续期共用，保证两处参数完全一致。"""

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


def find_session_user(
    session_cookie: str | None,
    db: sqlite3.Connection,
    request: Request | None = None,
    *,
    renew: bool = True,
) -> sqlite3.Row | None:
    if not session_cookie:
        return None
    token_hash = session_token_hash(session_cookie)
    row = db.execute(
        """
        SELECT u.id, u.username, u.role, s.expires_at, s.created_at
        FROM sessions AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires_at > CURRENT_TIMESTAMP
          AND u.is_active = 1
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        # 这里刻意不写库。无效或过期的 Cookie 是客户端可以随意构造的，让每个请求
        # 顺手删一遍会话表，等于把写操作暴露在读路径上。过期会话改由启动维护和
        # `py -m app.maintenance`（db.purge_expired_sessions）清理。
        return None
    # 绝对上限：滑动续期不能把一个会话无限延长下去，到点就作废、要求重新登录。
    deadline = session_hard_deadline(row["created_at"])
    if deadline is not None and datetime.now(UTC) >= deadline:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        db.commit()
        return None
    # 滑动续期：只要用户还在半程内活动过，就把有效期推回满值。
    # 数据库和浏览器 Cookie 必须一起顺延，否则浏览器会先一步把 Cookie 丢掉。
    # 这里只改数据库；Cookie 由 session_cookie_refresh_middleware 统一补上，
    # 因为下载/预览接口返回的是 FileResponse，依赖里设的响应头会被框架丢掉。
    if renew and session_needs_renewal(row["expires_at"]):
        renewed = session_expiry(deadline)
        # 已经顶到绝对上限时 renewed 不会更晚，这时不必白写一次数据库。
        if renewed > row["expires_at"]:
            db.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (renewed, token_hash),
            )
            db.commit()
            if request is not None:
                request.state.renewed_session_token = session_cookie
    return row


def current_user(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    row = find_session_user(session_cookie, db, request)
    if row is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return row


def optional_user(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row | None:
    return find_session_user(session_cookie, db, request)


def optional_user_no_renew(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row | None:
    """只查不续。退出登录时用：那一步马上要删会话，续期只会多写一次数据库。"""

    return find_session_user(session_cookie, db, renew=False)


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
        "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
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

    # 先校验口令再判断启用状态，避免匿名探测出哪些账户被停用。
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="账户已被停用，请联系管理员")

    clear_login_failures(db, username, client_ip)
    token, token_hash, expires_at = new_session_token()
    db.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (row["id"], token_hash, expires_at),
    )
    record_audit(db, row["id"], "login", "user", row["id"], "用户登录")
    db.commit()
    set_session_cookie(response, token)
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
    "/api/me/password",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.post(
    "/接口/我的密码",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="修改自己的密码",
    operation_id="修改自己的密码",
)
def change_my_password(
    payload: PasswordChange,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: sqlite3.Row = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    # 已登录不等于本人：别人拿到一个没锁屏的浏览器同样能点这个接口，
    # 所以必须再验一次当前密码。
    if row is None or not verify_password(
        payload.current_password, row["password_hash"]
    ):
        raise HTTPException(status_code=400, detail="当前密码不正确")

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(payload.new_password), user["id"]),
    )
    # 改完密码要把别处已经登录的会话全部作废（这是改密码的意义所在），
    # 但当前这一条保留，否则用户刚改完就被自己踢下线。
    if session_cookie:
        db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
            (user["id"], session_token_hash(session_cookie)),
        )
    else:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    record_audit(
        db,
        user["id"],
        "reset_password",
        "user",
        user["id"],
        "用户自助修改密码",
    )
    db.commit()


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
    user: sqlite3.Row | None = Depends(optional_user_no_renew),
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
