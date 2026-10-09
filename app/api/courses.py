import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import require_roles
from app.api.common import escape_like, page_response, subsequence_match
from app.db import (
    discard_staged_files,
    get_db,
    record_audit,
    restore_staged_files,
    stage_stored_files,
)
from app.schemas import (
    Course,
    CourseCreate,
    CourseDetail,
    CoursePage,
    CourseUpdate,
    serialize_tags,
)

router = APIRouter(tags=["课程"])


def row_to_course(row: sqlite3.Row) -> Course:
    return Course(**dict(row))


@router.get("/api/courses", include_in_schema=False)
@router.get(
    "/接口/课程",
    response_model=CoursePage,
    summary="查看课程列表",
    operation_id="查看课程列表",
)
def list_courses(
    关键词: str = Query("", max_length=80, description="按课程名、学院或标签筛选"),
    标签: str | None = Query(None, max_length=30, description="按标签精确筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: sqlite3.Connection = Depends(get_db),
) -> CoursePage:
    conditions: list[str] = []
    params: list[object] = []
    keyword = 关键词.strip()
    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        # 学院/标签可能是 NULL，NULL LIKE 不成立；但这里是 OR，课程名命中仍会返回。
        conditions.append(
            "(name LIKE ? ESCAPE '\\' OR college LIKE ? ESCAPE '\\' "
            "OR tags LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern, pattern])
    tag = (标签 or "").strip()
    if tag:
        # 标签是逗号分隔存的，两边补逗号再匹配 `,tag,`，避免「大二」误命中「大二班」。
        conditions.append("(',' || COALESCE(tags, '') || ',') LIKE ? ESCAPE '\\'")
        params.append(f"%,{escape_like(tag)},%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM courses {where}",  # noqa: S608 - 条件由内部白名单拼接
        params,
    ).fetchone()[0]
    if keyword and total == 0:
        # 正常子串没命中时，退一步按「简称子序列」匹配课程名（高数 → 高等数学）。
        if tag:
            candidates = db.execute(
                "SELECT id, name, college, version, tags FROM courses "
                "WHERE (',' || COALESCE(tags, '') || ',') LIKE ? ESCAPE '\\' "
                "ORDER BY id DESC",
                (f"%,{escape_like(tag)},%",),
            ).fetchall()
        else:
            candidates = db.execute(
                "SELECT id, name, college, version, tags FROM courses ORDER BY id DESC"
            ).fetchall()
        matched = [row for row in candidates if subsequence_match(keyword, row["name"])]
        start = (page - 1) * page_size
        end = start + page_size
        items = [row_to_course(row).model_dump() for row in matched[start:end]]
        return CoursePage(**page_response(items, len(matched), page, page_size))
    offset = (page - 1) * page_size
    rows = db.execute(
        f"""
        SELECT id, name, college, version, tags FROM courses {where}
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,  # noqa: S608 - 条件由内部白名单拼接
        (*params, page_size, offset),
    ).fetchall()
    items = [row_to_course(row).model_dump() for row in rows]
    return CoursePage(**page_response(items, total, page, page_size))


@router.get(
    "/api/courses/{course_id}",
    include_in_schema=False,
)
@router.get(
    "/接口/课程/{course_id}",
    response_model=CourseDetail,
    summary="查看课程详情",
    operation_id="查看课程详情",
)
def get_course(course_id: int, db: sqlite3.Connection = Depends(get_db)) -> CourseDetail:
    row = db.execute(
        """
        SELECT c.id, c.name, c.college, c.version, c.tags,
               COUNT(CASE WHEN f.status = 'approved' THEN f.id END) AS file_count
        FROM courses AS c
        LEFT JOIN files AS f ON f.course_id = c.id AND f.deleted_at IS NULL
        WHERE c.id = ?
        GROUP BY c.id
        """,
        (course_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return CourseDetail(**dict(row))


@router.post(
    "/api/courses",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/接口/课程",
    response_model=Course,
    status_code=status.HTTP_201_CREATED,
    summary="创建课程",
    operation_id="创建课程",
)
def create_course(
    course: CourseCreate,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> Course:
    # 课程名不允许重复：先查一次给出友好提示，唯一索引（若已建）再兜住并发。
    if db.execute(
        "SELECT 1 FROM courses WHERE name = ?", (course.name,)
    ).fetchone() is not None:
        raise HTTPException(status_code=409, detail="课程名称已存在")
    try:
        cursor = db.execute(
            "INSERT INTO courses (name, college, tags) VALUES (?, ?, ?)",
            (course.name, course.college, serialize_tags(course.tags)),
        )
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="课程名称已存在") from error
    record_audit(db, user["id"], "create", "course", cursor.lastrowid, course.name)
    db.commit()
    row = db.execute(
        "SELECT id, name, college, version, tags FROM courses WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return row_to_course(row)


@router.patch(
    "/api/courses/{course_id}",
    include_in_schema=False,
)
@router.patch(
    "/接口/课程/{course_id}",
    response_model=Course,
    summary="编辑课程",
    operation_id="编辑课程",
)
def update_course(
    course_id: int,
    course: CourseUpdate,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> Course:
    if not course.model_fields_set:
        raise HTTPException(status_code=422, detail="至少需要提供一个课程字段")
    values = course.model_dump(exclude_unset=True)
    expected_version = values.pop("version", None)
    if "tags" in values:
        values["tags"] = serialize_tags(values["tags"])
    if not values:
        raise HTTPException(status_code=422, detail="至少需要提供一个课程字段")
    if "name" in values:
        # 改名也不能与他人重名。
        clash = db.execute(
            "SELECT 1 FROM courses WHERE name = ? AND id != ?",
            (values["name"], course_id),
        ).fetchone()
        if clash is not None:
            raise HTTPException(status_code=409, detail="课程名称已存在")
    assignments = ", ".join(f"{field} = ?" for field in values)
    try:
        if expected_version is not None:
            # 原子乐观锁：把版本判断放进 WHERE，避免「先查后写」被并发覆盖。
            cursor = db.execute(
                f"UPDATE courses SET {assignments}, version = version + 1 "  # noqa: S608 - 字段名来自校验过的模型
                "WHERE id = ? AND version = ?",
                (*values.values(), course_id, expected_version),
            )
            if cursor.rowcount == 0:
                exists = db.execute(
                    "SELECT 1 FROM courses WHERE id = ?", (course_id,)
                ).fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="课程不存在")
                raise HTTPException(
                    status_code=409, detail="课程已被他人修改，请刷新后重试"
                )
        else:
            cursor = db.execute(
                f"UPDATE courses SET {assignments}, version = version + 1 WHERE id = ?",  # noqa: S608
                (*values.values(), course_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="课程不存在")
        record_audit(db, user["id"], "update", "course", course_id)
        db.commit()
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="课程名称已存在") from error
    except HTTPException:
        db.rollback()
        raise
    row = db.execute(
        "SELECT id, name, college, version, tags FROM courses WHERE id = ?",
        (course_id,),
    ).fetchone()
    return row_to_course(row)


@router.delete(
    "/api/courses/{course_id}",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/接口/课程/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除课程",
    operation_id="删除课程",
)
def delete_course(
    course_id: int,
    user: sqlite3.Row = Depends(require_roles("admin")),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    files = db.execute(
        "SELECT filename FROM files WHERE course_id = ?", (course_id,)
    ).fetchall()
    course = db.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    staged = []
    try:
        staged = stage_stored_files(files, db)
        cursor = db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="课程不存在")
        record_audit(db, user["id"], "delete", "course", course_id)
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_files(staged, db)
        raise
    discard_staged_files(staged, db)
