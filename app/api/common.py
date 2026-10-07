"""各 API 模块共用的分页、检索与日期处理助手。

这几个函数原先在 app/api/files.py 与 app/api/courses.py 里各有一份（page_response
甚至重复实现了两次），抽到这里后各模块只导入一份。
"""

from datetime import date

from fastapi import HTTPException


def page_response(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def escape_like(value: str) -> str:
    """转义 LIKE 通配符，避免用户输入的 % 或 _ 变成通配。"""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_date(value: str | None, field: str) -> date | None:
    """把 YYYY-MM-DD 解析为日期，空值返回 None，非法值直接 422。"""

    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail=f"{field}需要形如 2026-10-06 的日期"
        ) from error
