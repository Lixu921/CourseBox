"""操作记录（审计日志）查询。

此前全项目只有写入没有读取入口，管理员看不到谁在什么时候改了什么。
这里补上只读的列表接口，写入仍由 app/db.py 的 record_audit 负责。
"""

import sqlite3
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_roles
from app.api.common import escape_like, page_response, parse_date
from app.db import get_db
from app.schemas import AuditLog, AuditLogPage

router = APIRouter(tags=["审计"])

AuditAction = Literal[
    "create",
    "update",
    "delete",
    "download",
    "preview",
    "login",
    "logout",
    "reset_password",
    # 回收站相关动作。
    "restore",
    "purge",
    # 资料审核写入的动作就是审核结果本身，之前没列进来，导致按动作筛不到审核记录。
    "approved",
    "rejected",
]
AuditEntity = Literal["course", "file", "user"]

AUDIT_COLUMNS = """
    a.id, a.actor_id, a.action, a.entity_type, a.entity_id, a.detail, a.created_at,
    u.username AS actor_name
"""


def audit_response(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        actor_id=row["actor_id"],
        actor_name=row["actor_name"],
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        detail=row["detail"],
        created_at=row["created_at"],
    )


@router.get("/api/audit", include_in_schema=False)
@router.get(
    "/接口/审计",
    response_model=AuditLogPage,
    summary="查看操作记录",
    operation_id="查看操作记录",
)
def list_audit_logs(
    关键词: str = Query("", max_length=80, description="按操作人或操作详情筛选"),
    动作: AuditAction | None = Query(None, description="按动作筛选"),
    对象: AuditEntity | None = Query(None, description="按对象类型筛选"),
    起始时间: str | None = Query(None, description="不早于该日期（YYYY-MM-DD）"),
    结束时间: str | None = Query(None, description="不晚于该日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> AuditLogPage:
    conditions: list[str] = []
    params: list[object] = []

    keyword = 关键词.strip()
    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        conditions.append(
            "(u.username LIKE ? ESCAPE '\\' OR a.detail LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])
    if 动作 is not None:
        conditions.append("a.action = ?")
        params.append(动作)
    if 对象 is not None:
        conditions.append("a.entity_type = ?")
        params.append(对象)

    # created_at 由 SQLite 的 CURRENT_TIMESTAMP 写入，是 UTC 时间，这里按 UTC 日期比较。
    # 结束日期取次日零点做开区间，才能覆盖当天全部记录。
    start = parse_date(起始时间, "起始时间")
    end = parse_date(结束时间, "结束时间")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="起始时间不能晚于结束时间")
    if start is not None:
        conditions.append("a.created_at >= ?")
        params.append(f"{start.isoformat()} 00:00:00")
    if end is not None:
        conditions.append("a.created_at < ?")
        params.append(f"{(end + timedelta(days=1)).isoformat()} 00:00:00")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    # 操作人可能已被删除（actor_id 会被置为 NULL），所以用 LEFT JOIN。
    join = "LEFT JOIN users AS u ON u.id = a.actor_id"

    total = db.execute(
        f"SELECT COUNT(*) FROM audit_logs AS a {join} {where}",  # noqa: S608 - 条件由内部白名单拼接
        params,
    ).fetchone()[0]
    rows = db.execute(
        f"""
        SELECT {AUDIT_COLUMNS}
        FROM audit_logs AS a {join} {where}
        ORDER BY a.id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return AuditLogPage(
        **page_response([audit_response(row) for row in rows], total, page, page_size)
    )
