"""操作记录（审计日志）查询。

此前全项目只有写入没有读取入口，管理员看不到谁在什么时候改了什么。
这里补上只读的列表接口，写入仍由 app/db.py 的 record_audit 负责。
"""

import sqlite3
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_roles
from app.api.common import escape_like, page_response, parse_date
from app.config import get_settings
from app.csv_export import csv_response
from app.db import get_db, record_audit
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
    # 导出 CSV 本身也要留痕，否则「谁把整库清单带走了」查不到。
    "export",
]
AuditEntity = Literal["course", "file", "user", "audit"]

# 导出的 CSV 里给人看的动作名。新增动作忘记登记时退回原始英文值，
# 不会因为缺一个键就整个导出失败。
ACTION_LABELS = {
    "create": "新建",
    "update": "修改",
    "delete": "删除",
    "download": "下载",
    "preview": "预览",
    "login": "登录",
    "logout": "退出登录",
    "reset_password": "重置密码",
    "restore": "从回收站恢复",
    "purge": "彻底删除",
    "approved": "审核通过",
    "rejected": "审核拒绝",
    "export": "导出",
}
ENTITY_LABELS = {"course": "课程", "file": "资料", "user": "用户", "audit": "审计"}

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


def build_audit_filter(
    keyword: str,
    action: str | None,
    entity: str | None,
    start_text: str | None,
    end_text: str | None,
) -> tuple[str, list[object]]:
    """把列表与导出共用的筛选条件拼成 (where, params)。

    两个接口必须用同一套规则，否则「列表里看到 30 条、导出却是 12 条」这种
    对不上的现象会让人怀疑数据本身有问题。
    """

    conditions: list[str] = []
    params: list[object] = []

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        conditions.append(
            "(u.username LIKE ? ESCAPE '\\' OR a.detail LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])
    if action is not None:
        conditions.append("a.action = ?")
        params.append(action)
    if entity is not None:
        conditions.append("a.entity_type = ?")
        params.append(entity)

    # created_at 由 SQLite 的 CURRENT_TIMESTAMP 写入，是 UTC 时间，这里按 UTC 日期比较。
    # 结束日期取次日零点做开区间，才能覆盖当天全部记录。
    start = parse_date(start_text, "起始时间")
    end = parse_date(end_text, "结束时间")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="起始时间不能晚于结束时间")
    if start is not None:
        conditions.append("a.created_at >= ?")
        params.append(f"{start.isoformat()} 00:00:00")
    if end is not None:
        conditions.append("a.created_at < ?")
        params.append(f"{(end + timedelta(days=1)).isoformat()} 00:00:00")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


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
    where, params = build_audit_filter(关键词, 动作, 对象, 起始时间, 结束时间)
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


@router.get("/api/audit/export", include_in_schema=False)
@router.get(
    "/接口/审计导出",
    summary="导出操作记录（CSV）",
    operation_id="导出操作记录",
)
def export_audit_logs(
    关键词: str = Query("", max_length=80, description="按操作人或操作详情筛选"),
    动作: AuditAction | None = Query(None, description="按动作筛选"),
    对象: AuditEntity | None = Query(None, description="按对象类型筛选"),
    起始时间: str | None = Query(None, description="不早于该日期（YYYY-MM-DD）"),
    结束时间: str | None = Query(None, description="不晚于该日期（YYYY-MM-DD）"),
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> Response:
    where, params = build_audit_filter(关键词, 动作, 对象, 起始时间, 结束时间)
    limit = get_settings().export_max_rows
    rows = db.execute(
        f"""
        SELECT {AUDIT_COLUMNS}
        FROM audit_logs AS a LEFT JOIN users AS u ON u.id = a.actor_id
        {where} ORDER BY a.id DESC LIMIT ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, limit + 1),
    ).fetchall()
    # 多取一条来判断有没有超限。超限时报错而不是截断：被截断的清单最危险的地方
    # 是它看起来是完整的，拿去做合规材料会出事。
    if len(rows) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"匹配的操作记录超过 {limit} 条，请先用筛选条件缩小范围再导出",
        )

    record_audit(
        db,
        user["id"],
        "export",
        "audit",
        None,
        f"导出操作记录 {len(rows)} 条",
    )
    db.commit()
    return csv_response(
        "操作记录.csv",
        ("编号", "时间", "操作人", "动作", "对象", "对象编号", "详情"),
        (
            (
                row["id"],
                row["created_at"],
                row["actor_name"] or "（账户已删除）",
                ACTION_LABELS.get(row["action"], row["action"]),
                ENTITY_LABELS.get(row["entity_type"], row["entity_type"]),
                row["entity_id"] if row["entity_id"] is not None else "",
                row["detail"] or "",
            )
            for row in rows
        ),
    )

