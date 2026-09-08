import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "coursebox.db"
DEFAULT_UPLOADS_PATH = PROJECT_ROOT / "uploads"
DEFAULT_MAX_FILE_SIZE = 20 * 1024 * 1024
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin12345"

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


def database_path() -> Path:
    raw_value = os.getenv("COURSEBOX_DB")
    if raw_value and raw_value.strip():
        return Path(raw_value.strip()).expanduser()
    return DEFAULT_DB_PATH


def uploads_path() -> Path:
    raw_value = os.getenv("COURSEBOX_UPLOAD_DIR")
    if raw_value and raw_value.strip():
        return Path(raw_value.strip()).expanduser()
    return DEFAULT_UPLOADS_PATH


def max_file_size() -> int:
    raw_value = os.getenv("COURSEBOX_MAX_FILE_SIZE", str(DEFAULT_MAX_FILE_SIZE))
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_FILE_SIZE
    return value if value > 0 else DEFAULT_MAX_FILE_SIZE


def allowed_extensions() -> set[str]:
    raw_value = os.getenv("COURSEBOX_ALLOWED_EXTENSIONS")
    if not raw_value or not raw_value.strip():
        return DEFAULT_ALLOWED_EXTENSIONS.copy()
    extensions = set()
    for raw_extension in raw_value.split(","):
        extension = raw_extension.strip().lower()
        if extension:
            extensions.add(
                extension if extension.startswith(".") else f".{extension}"
            )
    return extensions or DEFAULT_ALLOWED_EXTENSIONS.copy()


def bootstrap_admin_username() -> str:
    value = os.getenv("COURSEBOX_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME).strip()
    return value or DEFAULT_ADMIN_USERNAME


def bootstrap_admin_password() -> str:
    value = os.getenv("COURSEBOX_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    return value if len(value) >= 8 else DEFAULT_ADMIN_PASSWORD
