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


class Course(BaseModel):
    id: int
    name: str
    college: str | None = None
    semester: str | None = None

