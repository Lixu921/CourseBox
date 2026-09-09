import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "coursebox.db"
DEFAULT_UPLOADS_PATH = PROJECT_ROOT / "uploads"
DEFAULT_MAX_FILE_SIZE = 20 * 1024 * 1024
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin12345"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MIN_FREE_SPACE = 100 * 1024 * 1024
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

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


def get_settings() -> Settings:
    log_level = os.getenv("COURSEBOX_LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = DEFAULT_LOG_LEVEL
    host = os.getenv("COURSEBOX_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    admin_username = (
        os.getenv("COURSEBOX_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME).strip()
        or DEFAULT_ADMIN_USERNAME
    )
    admin_password = os.getenv(
        "COURSEBOX_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD
    )
    if len(admin_password) < 8:
        admin_password = DEFAULT_ADMIN_PASSWORD
    return Settings(
        database_path=_path_from_env("COURSEBOX_DB", DEFAULT_DB_PATH),
        uploads_path=_path_from_env("COURSEBOX_UPLOAD_DIR", DEFAULT_UPLOADS_PATH),
        max_file_size=_positive_int("COURSEBOX_MAX_FILE_SIZE", DEFAULT_MAX_FILE_SIZE),
        allowed_extensions=_extensions_from_env(),
        admin_username=admin_username,
        admin_password=admin_password,
        log_level=log_level,
        min_free_space=_positive_int(
            "COURSEBOX_MIN_FREE_SPACE", DEFAULT_MIN_FREE_SPACE
        ),
        host=host,
        port=_positive_int("COURSEBOX_PORT", DEFAULT_PORT),
    )
