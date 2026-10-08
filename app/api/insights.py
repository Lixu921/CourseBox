"""首页洞察：热门资料、最新资料，以及管理员概览。

热门/最新是公开只读接口；概览仅管理员。全部是聚合查询，不写库。
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_roles
from app.db import get_db
from app.schemas import Course, InsightFile, InsightFileList, Overview, OverviewFiles

router = APIRouter(tags=["概览"])

INSIGHT_COLUMNS = """
    f.id, f.course_id, f.title, f.original_name, f.size, f.upload_time,
    f.download_count, f.status,
    c.id AS c_id, c.name AS c_name, c.college AS c_college,
    c.semester AS c_semester, c.version AS c_version, c.tags AS c_tags
"""
INSIGHT_WHERE = "f.status = 'approved' AND f.deleted_at IS NULL"


def insight_response(row: sqlite3.Row) -> InsightFile:
    return InsightFile(
        id=row["id"],
        course_id=row["course_id"],
        title=row["title"],
        original_name=row["original_name"],
        size=row["size"],
        upload_time=row["upload_time"],
        download_count=row["download_count"],
        status=row["status"],
        course=Course(
            id=row["c_id"],
            name=row["c_name"],
            college=row["c_college"],
            semester=row["c_semester"],
            version=row["c_version"],
            tags=row["c_tags"],
        ),
    )


def _list_insight_files(order: str, 数量: int, db: sqlite3.Connection) -> InsightFileList:
    rows = db.execute(
        f"SELECT {INSIGHT_COLUMNS} "  # noqa: S608 - 列名来自内部常量
        f"FROM files AS f JOIN courses AS c ON c.id = f.course_id "
        f"WHERE {INSIGHT_WHERE} ORDER BY {order} LIMIT ?",  # noqa: S608 - order 来自内部白名单
        (数量,),
    ).fetchall()
    return InsightFileList(items=[insight_response(row) for row in rows])


@router.get("/api/hot", include_in_schema=False)
@router.get(
    "/接口/热门",
    response_model=InsightFileList,
    summary="热门资料",
    operation_id="热门资料",
)
def hot_files(
    数量: int = Query(10, ge=1, le=50, description="返回条数"),
    db: sqlite3.Connection = Depends(get_db),
) -> InsightFileList:
    return _list_insight_files("f.download_count DESC, f.id DESC", 数量, db)


@router.get("/api/recent", include_in_schema=False)
@router.get(
    "/接口/最新",
    response_model=InsightFileList,
    summary="最新资料",
    operation_id="最新资料",
)
def recent_files(
    数量: int = Query(10, ge=1, le=50, description="返回条数"),
    db: sqlite3.Connection = Depends(get_db),
) -> InsightFileList:
    return _list_insight_files("f.id DESC", 数量, db)


@router.get("/api/overview", include_in_schema=False)
@router.get(
    "/接口/概览",
    response_model=Overview,
    summary="站点概览",
    operation_id="站点概览",
)
def overview(
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> Overview:
    def count(sql: str) -> int:
        return db.execute(sql).fetchone()[0]

    approved = count(
        "SELECT COUNT(*) FROM files WHERE status = 'approved' AND deleted_at IS NULL"
    )
    pending = count(
        "SELECT COUNT(*) FROM files WHERE status = 'pending' AND deleted_at IS NULL"
    )
    rejected = count(
        "SELECT COUNT(*) FROM files WHERE status = 'rejected' AND deleted_at IS NULL"
    )
    return Overview(
        courses=count("SELECT COUNT(*) FROM courses"),
        files=OverviewFiles(
            approved=approved,
            pending=pending,
            rejected=rejected,
            total=approved + pending + rejected,
        ),
        trash=count("SELECT COUNT(*) FROM files WHERE deleted_at IS NOT NULL"),
        users_total=count("SELECT COUNT(*) FROM users"),
        users_active=count("SELECT COUNT(*) FROM users WHERE is_active = 1"),
        storage_bytes=count(
            "SELECT COALESCE(SUM(size), 0) FROM files WHERE deleted_at IS NULL"
        ),
        downloads=count("SELECT COALESCE(SUM(download_count), 0) FROM files"),
    )
