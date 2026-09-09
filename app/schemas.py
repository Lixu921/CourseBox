from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.auth import hash_password


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    college: str | None = Field(default=None, max_length=120)
    semester: str | None = Field(default=None, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("课程名称必须是文本")
        value = value.strip()
        if not value:
            raise ValueError("课程名称不能为空")
        return value

    @field_validator("college", "semester", mode="before")
    @classmethod
    def optional_text_is_normalized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("字段必须是文本")
        value = value.strip()
        return value or None


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    college: str | None = Field(default=None, max_length=120)
    semester: str | None = Field(default=None, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("课程名称不能为空")
        if not isinstance(value, str):
            raise ValueError("课程名称必须是文本")
        value = value.strip()
        if not value:
            raise ValueError("课程名称不能为空")
        return value

    @field_validator("college", "semester", mode="before")
    @classmethod
    def optional_text_is_normalized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("字段必须是文本")
        value = value.strip()
        return value or None


class FileUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("资料标题必须是文本")
        value = value.strip()
        if not value:
            raise ValueError("资料标题不能为空")
        return value


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("用户名必须是文本")
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        return value


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=8, max_length=200)
    role: Literal["admin", "uploader", "viewer"] = "viewer"

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("用户名必须是文本")
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        return value

    def password_hash(self) -> str:
        return hash_password(self.password)


class User(BaseModel):
    id: int
    username: str
    role: Literal["admin", "uploader", "viewer"]


class FileReview(BaseModel):
    status: Literal["approved", "rejected"]


class Course(BaseModel):
    id: int
    name: str
    college: str | None = None
    semester: str | None = None


class CourseDetail(Course):
    file_count: int = 0


class PageInfo(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class CoursePage(PageInfo):
    items: list[Course]


class FilePage(PageInfo):
    items: list[dict]
