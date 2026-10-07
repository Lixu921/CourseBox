import logging
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "coursebox.db"
DEFAULT_UPLOADS_PATH = PROJECT_ROOT / "uploads"
DEFAULT_MAX_FILE_SIZE = 20 * 1024 * 1024
DEFAULT_ADMIN_USERNAME = "admin"
# 仅作为开发环境兜底；生产环境未显式配置会直接拒绝启动，见 _admin_password()。
DEFAULT_ADMIN_PASSWORD = "admin12345"  # noqa: S105
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MIN_FREE_SPACE = 100 * 1024 * 1024
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_ENV = "development"
PRODUCTION_ENVS = {"production", "prod"}
MIN_ADMIN_PASSWORD_LENGTH = 8
DEFAULT_LOGIN_MAX_ATTEMPTS = 5
DEFAULT_LOGIN_LOCKOUT_SECONDS = 300
DEFAULT_MAX_COURSE_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_AUDIT_RETENTION_DAYS = 90
# 回收站保留天数：删掉的资料先在这里放着，超期才真正从磁盘删除。
DEFAULT_TRASH_RETENTION_DAYS = 30
# 每分钟每 IP 的请求上限。默认值刻意放宽：正常浏览远达不到，
# 只用来挡住脚本级的突发流量，避免误伤多人共用同一个出口 IP 的校园网。
DEFAULT_RATE_LIMIT_ENABLED = True
DEFAULT_RATE_LIMIT_PER_MINUTE = 300
# 单次 CSV 导出的行数上限。超过就报错让用户先用筛选条件缩小范围，
# 而不是悄悄截断——被截断的清单最危险的地方是它看起来是完整的。
DEFAULT_EXPORT_MAX_ROWS = 5000

logger = logging.getLogger("coursebox.config")

# Keep the allowlist broad enough for ordinary course material while rejecting
# executable formats by default.
DEFAULT_ALLOWED_EXTENSIONS = {
    ".7z",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".md",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}


def load_env_file(path: Path = ENV_FILE) -> None:
    """Load simple KEY=VALUE entries without overriding real environment values."""

    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        name, value = candidate.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or name in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name] = value


load_env_file()


def database_path() -> Path:
    return get_settings().database_path


def uploads_path() -> Path:
    return get_settings().uploads_path


def max_file_size() -> int:
    return get_settings().max_file_size


def allowed_extensions() -> set[str]:
    return get_settings().allowed_extensions.copy()


def bootstrap_admin_username() -> str:
    return get_settings().admin_username


def bootstrap_admin_password() -> str:
    return get_settings().admin_password


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return value if value > 0 else default


def _quota_bytes(name: str, default: int) -> int:
    """配额配置，0 表示不限制，非法值回退默认值。"""

    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value or not value.strip():
        return default
    path = Path(value.strip()).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _extensions_from_env() -> set[str]:
    raw_value = os.getenv("COURSEBOX_ALLOWED_EXTENSIONS")
    if not raw_value or not raw_value.strip():
        return DEFAULT_ALLOWED_EXTENSIONS.copy()
    extensions = {
        extension if extension.startswith(".") else f".{extension}"
        for raw_extension in raw_value.split(",")
        if (extension := raw_extension.strip().lower())
    }
    return extensions or DEFAULT_ALLOWED_EXTENSIONS.copy()


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# get_settings() 每个请求会被多个中间件各调用一次，而默认密码的告警只需要提示一次，
# 否则开发环境的日志会被同一条警告刷满、把真正的请求日志挤掉。
_default_password_warned = False


def _warn_default_password_once() -> None:
    global _default_password_warned
    if _default_password_warned:
        return
    _default_password_warned = True
    logger.warning(
        "COURSEBOX_ADMIN_PASSWORD 未设置，开发环境暂用内置默认密码；"
        "请勿在可被访问的环境中使用默认密码。",
        extra={"event": "insecure_default_password"},
    )


def _admin_password(is_production: bool) -> str:
    """生产环境绝不回退到默认密码，配置缺失或过短一律拒绝启动。"""

    configured = (os.getenv("COURSEBOX_ADMIN_PASSWORD") or "").strip()
    if not configured:
        if is_production:
            raise RuntimeError(
                "生产环境必须设置 COURSEBOX_ADMIN_PASSWORD"
                f"（至少 {MIN_ADMIN_PASSWORD_LENGTH} 位），已拒绝启动。"
            )
        _warn_default_password_once()
        return DEFAULT_ADMIN_PASSWORD
    if len(configured) < MIN_ADMIN_PASSWORD_LENGTH:
        raise RuntimeError(
            f"COURSEBOX_ADMIN_PASSWORD 至少需要 {MIN_ADMIN_PASSWORD_LENGTH} 位，已拒绝启动。"
        )
    return configured


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    database_path: Path
    uploads_path: Path
    max_file_size: int
    allowed_extensions: set[str]
    admin_username: str
    admin_password: str
    log_level: str
    min_free_space: int
    host: str
    port: int
    environment: str
    cookie_secure: bool
    login_max_attempts: int
    login_lockout_seconds: int
    max_course_bytes: int
    max_total_bytes: int
    audit_retention_days: int
    trash_retention_days: int
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    export_max_rows: int

    @property
    def is_production(self) -> bool:
        return self.environment in PRODUCTION_ENVS


def get_settings() -> Settings:
    log_level = os.getenv("COURSEBOX_LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = DEFAULT_LOG_LEVEL
    host = os.getenv("COURSEBOX_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    admin_username = (
        os.getenv("COURSEBOX_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME).strip()
        or DEFAULT_ADMIN_USERNAME
    )
    environment = os.getenv("COURSEBOX_ENV", DEFAULT_ENV).strip().lower() or DEFAULT_ENV
    is_production = environment in PRODUCTION_ENVS
    return Settings(
        database_path=_path_from_env("COURSEBOX_DB", DEFAULT_DB_PATH),
        uploads_path=_path_from_env("COURSEBOX_UPLOAD_DIR", DEFAULT_UPLOADS_PATH),
        max_file_size=_positive_int("COURSEBOX_MAX_FILE_SIZE", DEFAULT_MAX_FILE_SIZE),
        allowed_extensions=_extensions_from_env(),
        admin_username=admin_username,
        admin_password=_admin_password(is_production),
        log_level=log_level,
        min_free_space=_positive_int(
            "COURSEBOX_MIN_FREE_SPACE", DEFAULT_MIN_FREE_SPACE
        ),
        host=host,
        port=_positive_int("COURSEBOX_PORT", DEFAULT_PORT),
        environment=environment,
        # 局域网通常走 http，默认值随环境走，避免开发环境登录拿不到 Cookie。
        cookie_secure=_bool_from_env("COURSEBOX_COOKIE_SECURE", is_production),
        login_max_attempts=_positive_int(
            "COURSEBOX_LOGIN_MAX_ATTEMPTS", DEFAULT_LOGIN_MAX_ATTEMPTS
        ),
        login_lockout_seconds=_positive_int(
            "COURSEBOX_LOGIN_LOCKOUT_SECONDS", DEFAULT_LOGIN_LOCKOUT_SECONDS
        ),
        max_course_bytes=_quota_bytes(
            "COURSEBOX_MAX_COURSE_BYTES", DEFAULT_MAX_COURSE_BYTES
        ),
        max_total_bytes=_quota_bytes(
            "COURSEBOX_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL_BYTES
        ),
        audit_retention_days=_positive_int(
            "COURSEBOX_AUDIT_RETENTION_DAYS", DEFAULT_AUDIT_RETENTION_DAYS
        ),
        trash_retention_days=_positive_int(
            "COURSEBOX_TRASH_RETENTION_DAYS", DEFAULT_TRASH_RETENTION_DAYS
        ),
        rate_limit_enabled=_bool_from_env(
            "COURSEBOX_RATE_LIMIT_ENABLED", DEFAULT_RATE_LIMIT_ENABLED
        ),
        rate_limit_per_minute=_positive_int(
            "COURSEBOX_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE
        ),
        export_max_rows=_positive_int(
            "COURSEBOX_EXPORT_MAX_ROWS", DEFAULT_EXPORT_MAX_ROWS
        ),
    )
