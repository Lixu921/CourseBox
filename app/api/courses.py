import sqlite3

from fastapi import APIRouter, Depends, status

from app.db import get_db
from app.schemas import Course, CourseCreate


router = APIRouter(prefix="/api/courses", tags=["courses"])


def row_to_course(row: sqlite3.Row) -> Course:
    return Course(**dict(row))


@router.get("", response_model=list[Course])
def list_courses(db: sqlite3.Connection = Depends(get_db)) -> list[Course]:
    rows = db.execute(
        "SELECT id, name, college, semester FROM courses ORDER BY id DESC"
    ).fetchall()
    return [row_to_course(row) for row in rows]


@router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
def create_course(
    course: CourseCreate, db: sqlite3.Connection = Depends(get_db)
) -> Course:
    cursor = db.execute(
        "INSERT INTO courses (name, college, semester) VALUES (?, ?, ?)",
        (course.name, course.college, course.semester),
    )
    db.commit()
    row = db.execute(
        "SELECT id, name, college, semester FROM courses WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return row_to_course(row)

