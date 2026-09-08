from pydantic import BaseModel, Field, field_validator


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1)
    college: str | None = None
    semester: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("课程名称不能为空")
        return value


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    college: str | None = None
    semester: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("课程名称不能为空")
        return value


class FileUpdate(BaseModel):
    title: str = Field(..., min_length=1)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("资料标题不能为空")
        return value


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
