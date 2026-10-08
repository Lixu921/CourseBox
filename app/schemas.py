from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth import hash_password

# 课程标签：逗号分隔存一列。给个数与长度的上限，避免标签被当成第二段描述来写。
MAX_TAGS = 10
MAX_TAG_LENGTH = 30


def normalize_tags(value: object) -> list[str] | None:
    """把标签规整成去重、去空、限长的列表；None 表示「未提供」。"""

    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        raise ValueError("标签必须是文本列表")
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("标签必须是文本")
        tag = raw.strip()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"单个标签不能超过 {MAX_TAG_LENGTH} 个字符")
        if tag not in result:
            result.append(tag)
    if len(result) > MAX_TAGS:
        raise ValueError(f"标签最多 {MAX_TAGS} 个")
    return result


def serialize_tags(tags: list[str] | None) -> str | None:
    """把标签列表拼回库里的逗号分隔格式。"""

    return ",".join(tags) if tags else None


def parse_tags(value: object) -> list[str]:
    """把库里的逗号分隔标签读回列表。"""

    if not value or not isinstance(value, str):
        return []
    return [tag for tag in (part.strip() for part in value.split(",")) if tag]


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    college: str | None = Field(default=None, max_length=120)
    semester: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_normalized(cls, value: object) -> list[str] | None:
        return normalize_tags(value)

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
    tags: list[str] | None = None
    # 客户端看到并基于其编辑的版本号；不传则退化为「后写覆盖」。
    version: int | None = Field(default=None, ge=1)

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_normalized(cls, value: object) -> list[str] | None:
        return normalize_tags(value)

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
    # 客户端看到并基于其编辑的版本号；不传则退化为「后写覆盖」。
    version: int | None = Field(default=None, ge=1)

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


class UserAdmin(User):
    """管理员视角的用户信息，比公开的 User 多出启用状态与统计字段。"""

    is_active: bool = True
    created_at: str | None = None
    upload_count: int = 0


class UserUpdate(BaseModel):
    role: Literal["admin", "uploader", "viewer"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "UserUpdate":
        if self.role is None and self.is_active is None:
            raise ValueError("至少要修改角色或启用状态")
        return self


class PasswordReset(BaseModel):
    password: str = Field(..., min_length=8, max_length=200)


class PasswordChange(BaseModel):
    """用户自助改密码：必须带当前密码，新密码沿用管理员重置时的长度下限。"""

    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)

    @model_validator(mode="after")
    def new_password_must_differ(self) -> "PasswordChange":
        # 新密码和当前密码一样时，改了等于没改，却会把其它设备上的会话全部踢掉，
        # 属于「用户没意识到自己做了什么」的典型，直接拒绝更清楚。
        if self.new_password == self.current_password:
            raise ValueError("新密码不能与当前密码相同")
        return self


class FileReview(BaseModel):
    status: Literal["approved", "rejected"]


# 批量操作一次最多处理这么多条：既够管理员一次勾一页，又不会让单个请求
# 拿着几百条编号把连接占太久。
BATCH_MAX_ITEMS = 200


class BatchItemResult(BaseModel):
    id: int
    ok: bool
    message: str = ""


class BatchResult(BaseModel):
    """批量操作结果：逐条回报，部分失败时能看出是哪些失败了。"""

    succeeded: int
    failed: int
    items: list[BatchItemResult]

    @classmethod
    def from_items(cls, items: list[BatchItemResult]) -> "BatchResult":
        succeeded = sum(1 for item in items if item.ok)
        return cls(
            succeeded=succeeded,
            failed=len(items) - succeeded,
            items=items,
        )


class BatchIds(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=BATCH_MAX_ITEMS)


class UserBatchUpdate(BatchIds):
    action: Literal["enable", "disable", "role"]
    role: Literal["admin", "uploader", "viewer"] | None = None

    @model_validator(mode="after")
    def role_required_for_role_action(self) -> "UserBatchUpdate":
        if self.action == "role" and self.role is None:
            raise ValueError("批量修改角色时必须指定目标角色")
        return self


class FileBatchReview(BatchIds):
    status: Literal["approved", "rejected"]


class Course(BaseModel):
    id: int
    name: str
    college: str | None = None
    semester: str | None = None
    # 编辑乐观锁：客户端带着自己看到的版本号回传，服务端比对后决定是否放行。
    version: int = 1
    tags: list[str] = []

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_parsed(cls, value: object) -> list[str]:
        return parse_tags(value)


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


class CourseQuota(BaseModel):
    """课程上传配额明细。limit / remaining 为 None 表示该项没有设置上限。"""

    course_id: int
    allowed_bytes: int
    reason: str
    max_file_size: int
    course_limit: int | None = None
    course_used: int
    course_remaining: int | None = None
    site_limit: int | None = None
    site_used: int
    site_remaining: int | None = None
    user_limit: int | None = None
    user_used: int = 0
    user_remaining: int | None = None
    disk_free: int | None = None


class TrashFile(BaseModel):
    """回收站里的一条资料。deleted_at 是移入回收站的时间，删除人可能已不存在。"""

    id: int
    course_id: int
    course_name: str | None = None
    title: str
    original_name: str
    size: int
    upload_time: str
    status: str
    deleted_at: str
    deleted_by_name: str | None = None


class TrashFilePage(PageInfo):
    items: list[TrashFile]


class UserPage(PageInfo):
    items: list[UserAdmin]


class AuditLog(BaseModel):
    """一条操作记录。操作人被删除后 actor_id / actor_name 为 None。"""

    id: int
    actor_id: int | None = None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    detail: str | None = None
    created_at: str


class AuditLogPage(PageInfo):
    items: list[AuditLog]


# 分享链接的有效天数上限。过期后分享页打不开，但资料本身仍是公开可读的（见 README 已知局限）。
MAX_SHARE_DAYS = 90


class ShareCreate(BaseModel):
    days: int = Field(default=7, ge=1, le=MAX_SHARE_DAYS)
    note: str | None = Field(default=None, max_length=120)


class ShareLink(BaseModel):
    id: int
    token: str
    url: str
    note: str | None = None
    created_at: str
    expires_at: str


class ShareView(BaseModel):
    """分享页看到的内容：课程信息 + 该课程已通过的资料列表。"""

    course: Course
    files: list[dict]
    note: str | None = None
    expires_at: str
