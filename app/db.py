import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Generator

from app.config import (
    bootstrap_admin_password,
    bootstrap_admin_username,
    database_path,
    uploads_path,
)

# Kept as a compatibility alias for callers that imported the old constant.
UPLOADS_PATH = uploads_path()
logger = logging.getLogger("coursebox")
# 已解锁的登录失败记录保留一天，够用来累计连续失败又不至于无限堆积。
LOGIN_ATTEMPT_RETENTION_SECONDS = 24 * 60 * 60


def init_db(connection: sqlite3.Connection | None = None) -> None:
    close_connection = connection is None
    if connection is None:
        path = database_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)

    try:
        configure_connection(connection)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                college TEXT,
                semester TEXT
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                upload_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                mime_type TEXT,
                sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'approved',
                uploaded_by INTEGER,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'uploader', 'viewer')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS file_deletion_journal (
                staged_name TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT NOT NULL,
                client_ip TEXT NOT NULL,
                failed_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (username, client_ip)
            );
            """
        )
        migrate_files_table(connection)
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_courses_name ON courses(name);
            CREATE INDEX IF NOT EXISTS idx_files_course_id ON files(course_id);
            CREATE INDEX IF NOT EXISTS idx_files_title ON files(title);
            CREATE INDEX IF NOT EXISTS idx_files_original_name ON files(original_name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_files_course_sha256
                ON files(course_id, sha256) WHERE sha256 IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
            CREATE INDEX IF NOT EXISTS idx_files_uploaded_by ON files(uploaded_by);
            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_login_attempts_locked_until
                ON login_attempts(locked_until);
            """
        )
        ensure_fts(connection)
        ensure_bootstrap_admin(connection)
        connection.commit()
    finally:
        if close_connection:
            connection.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        init_db(connection)
        yield connection
    finally:
        connection.close()


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")


def migrate_files_table(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(files)").fetchall()
    }
    migrations = {
        "mime_type": "ALTER TABLE files ADD COLUMN mime_type TEXT",
        "sha256": "ALTER TABLE files ADD COLUMN sha256 TEXT",
        "status": "ALTER TABLE files ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
        "uploaded_by": "ALTER TABLE files ADD COLUMN uploaded_by INTEGER",
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


def ensure_bootstrap_admin(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
        return
    from app.auth import hash_password

    connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
        (bootstrap_admin_username(), hash_password(bootstrap_admin_password())),
    )


def record_audit(
    connection: sqlite3.Connection,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (actor_id, action, entity_type, entity_id, detail),
    )


def login_lock_remaining(
    connection: sqlite3.Connection, username: str, client_ip: str
) -> int:
    """返回当前登录键剩余锁定秒数，未锁定返回 0。"""

    row = connection.execute(
        """
        SELECT CAST(
                   strftime('%s', locked_until) - strftime('%s', 'now') AS INTEGER
               ) AS remaining
        FROM login_attempts
        WHERE username = ? AND client_ip = ?
          AND locked_until IS NOT NULL AND locked_until > CURRENT_TIMESTAMP
        """,
        (username, client_ip),
    ).fetchone()
    if row is None or row["remaining"] is None:
        return 0
    return max(int(row["remaining"]), 0)


def register_login_failure(
    connection: sqlite3.Connection,
    username: str,
    client_ip: str,
    max_attempts: int,
    lockout_seconds: int,
) -> int:
    """累计一次失败；达到阈值时写入锁定时长，返回当前失败次数。"""

    connection.execute(
        """
        INSERT INTO login_attempts (username, client_ip, failed_count)
        VALUES (?, ?, 1)
        ON CONFLICT(username, client_ip) DO UPDATE SET
            failed_count = failed_count + 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (username, client_ip),
    )
    row = connection.execute(
        "SELECT failed_count FROM login_attempts WHERE username = ? AND client_ip = ?",
        (username, client_ip),
    ).fetchone()
    failed_count = int(row["failed_count"]) if row is not None else 1
    if failed_count >= max_attempts:
        connection.execute(
            """
            UPDATE login_attempts
            SET locked_until = datetime('now', ?)
            WHERE username = ? AND client_ip = ?
            """,
            (f"+{lockout_seconds} seconds", username, client_ip),
        )
    connection.commit()
    return failed_count


def clear_login_failures(
    connection: sqlite3.Connection, username: str, client_ip: str
) -> None:
    connection.execute(
        "DELETE FROM login_attempts WHERE username = ? AND client_ip = ?",
        (username, client_ip),
    )
    connection.commit()


def purge_login_attempts(connection: sqlite3.Connection, keep_seconds: int) -> int:
    """清理已解锁且长期未活动的登录记录，避免表无限增长。"""

    cursor = connection.execute(
        """
        DELETE FROM login_attempts
        WHERE (locked_until IS NULL OR locked_until <= CURRENT_TIMESTAMP)
          AND updated_at < datetime('now', ?)
        """,
        (f"-{keep_seconds} seconds",),
    )
    connection.commit()
    return cursor.rowcount or 0


def purge_audit_logs(connection: sqlite3.Connection, retention_days: int) -> int:
    """删除超过保留期的审计日志；retention_days 不大于 0 时保留全部。"""

    if retention_days <= 0:
        return 0
    cursor = connection.execute(
        "DELETE FROM audit_logs WHERE created_at < datetime('now', ?)",
        (f"-{retention_days} days",),
    )
    connection.commit()
    return cursor.rowcount or 0


def stored_file_path(filename: str) -> Path | None:
    root = uploads_path().resolve()
    path = (root / filename).resolve()
    return path if root in path.parents else None


def stage_stored_files(
    rows: list[sqlite3.Row], connection: sqlite3.Connection
) -> list[tuple[Path, Path]]:
    """Move files aside while a deletion transaction is still reversible."""

    root = uploads_path().resolve()
    staged: list[tuple[Path, Path]] = []
    candidates: list[tuple[Path, Path, str]] = []
    for row in rows:
        path = stored_file_path(row["filename"])
        if path is None or not path.exists():
            continue
        if not path.is_file():
            raise OSError(f"stored path is not a regular file: {path}")
        staged_path = root / f".coursebox-deleting-{uuid.uuid4().hex}"
        candidates.append((path, staged_path, row["filename"]))

    if not candidates:
        return staged

    connection.executemany(
        "INSERT INTO file_deletion_journal (staged_name, original_name) VALUES (?, ?)",
        [(staged.name, original_name) for _, staged, original_name in candidates],
    )
    connection.commit()
    try:
        for original, staged_path, _ in candidates:
            original.replace(staged_path)
            staged.append((original, staged_path))
    except Exception:
        restore_staged_files(staged, connection)
        remaining = [staged_path.name for _, staged_path, _ in candidates]
        clear_deletion_journal(connection, remaining)
        raise
    return staged


def restore_staged_files(
    staged: list[tuple[Path, Path]], connection: sqlite3.Connection
) -> None:
    restored_names: list[str] = []
    for original_path, staged_path in reversed(staged):
        if not staged_path.exists():
            continue
        try:
            staged_path.replace(original_path)
            restored_names.append(staged_path.name)
        except OSError as error:
            logger.error(
                "staged file restore failed: %s",
                error,
                extra={"event": "file_cleanup"},
            )
    clear_deletion_journal(connection, restored_names)


def discard_staged_files(
    staged: list[tuple[Path, Path]], connection: sqlite3.Connection
) -> None:
    discarded_names: list[str] = []
    for _, staged_path in staged:
        try:
            staged_path.unlink(missing_ok=True)
            discarded_names.append(staged_path.name)
        except OSError as error:
            logger.warning(
                "staged file cleanup failed: %s",
                error,
                extra={"event": "file_cleanup"},
            )
    clear_deletion_journal(connection, discarded_names)


def clear_deletion_journal(
    connection: sqlite3.Connection, staged_names: list[str]
) -> None:
    if not staged_names:
        return
    placeholders = ", ".join("?" for _ in staged_names)
    try:
        connection.execute(
            f"DELETE FROM file_deletion_journal WHERE staged_name IN ({placeholders})",
            staged_names,
        )
        connection.commit()
    except sqlite3.Error as error:
        connection.rollback()
        logger.warning(
            "deletion journal cleanup failed: %s",
            error,
            extra={"event": "file_cleanup"},
        )


def cleanup_staged_files(connection: sqlite3.Connection) -> None:
    """Recover deletions interrupted before or after their database commit."""

    root = uploads_path().resolve()
    rows = connection.execute(
        "SELECT staged_name, original_name FROM file_deletion_journal"
    ).fetchall()
    handled_names: list[str] = []
    for row in rows:
        staged_path = stored_file_path(row["staged_name"])
        original_path = stored_file_path(row["original_name"])
        if staged_path is None or original_path is None:
            action = "discard"
        else:
            referenced = connection.execute(
                "SELECT 1 FROM files WHERE filename = ? LIMIT 1",
                (row["original_name"],),
            ).fetchone() is not None
            action = "restore" if referenced else "discard"
        try:
            if staged_path is not None and action == "restore" and staged_path.is_file():
                if original_path is not None and not original_path.exists():
                    staged_path.replace(original_path)
                else:
                    staged_path.unlink(missing_ok=True)
            elif staged_path is not None and action == "discard":
                staged_path.unlink(missing_ok=True)
            if staged_path is None or not staged_path.exists():
                handled_names.append(row["staged_name"])
        except OSError as error:
            logger.warning(
                "staged file recovery failed: %s",
                error,
                extra={"event": "file_cleanup"},
            )
    clear_deletion_journal(connection, handled_names)

    # Clean temporary files created by older versions that did not have a journal.
    try:
        journal_names = {
            row["staged_name"]
            for row in connection.execute(
                "SELECT staged_name FROM file_deletion_journal"
            ).fetchall()
        }
        for path in root.glob(".coursebox-deleting-*"):
            if path.name in journal_names:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                logger.warning(
                    "orphaned staged file cleanup failed: %s",
                    error,
                    extra={"event": "file_cleanup"},
                )
    except OSError as error:
        logger.warning(
            "staged file recovery scan failed: %s",
            error,
            extra={"event": "file_cleanup"},
        )


FTS_TABLE_SQL = """
    CREATE VIRTUAL TABLE files_fts USING fts5(
        title, original_name, content='files', content_rowid='id', tokenize='trigram'
    )
"""
FTS_TRIGGERS = ("files_fts_after_insert", "files_fts_after_update", "files_fts_after_delete")
FTS_TRIGGER_SQL = """
    CREATE TRIGGER IF NOT EXISTS files_fts_after_insert
    AFTER INSERT ON files BEGIN
        INSERT INTO files_fts(rowid, title, original_name)
        VALUES (new.id, new.title, new.original_name);
    END;
    CREATE TRIGGER IF NOT EXISTS files_fts_after_update
    AFTER UPDATE OF title, original_name ON files BEGIN
        INSERT INTO files_fts(files_fts, rowid, title, original_name)
        VALUES ('delete', old.id, old.title, old.original_name);
        INSERT INTO files_fts(rowid, title, original_name)
        VALUES (new.id, new.title, new.original_name);
    END;
    CREATE TRIGGER IF NOT EXISTS files_fts_after_delete
    AFTER DELETE ON files BEGIN
        INSERT INTO files_fts(files_fts, rowid, title, original_name)
        VALUES ('delete', old.id, old.title, old.original_name);
    END;
"""


def ensure_fts(connection: sqlite3.Connection) -> bool:
    """确保全文索引存在；旧版默认分词器无法命中中文子串，需要重建为 trigram。"""

    try:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'files_fts'"
        ).fetchone()
        existing_sql = row["sql"] if row is not None else None
        needs_create = existing_sql is None
        if not needs_create and "trigram" not in (existing_sql or "").lower():
            for trigger in FTS_TRIGGERS:
                connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            connection.execute("DROP TABLE files_fts")
            needs_create = True
        if needs_create:
            connection.execute(FTS_TABLE_SQL)
        connection.executescript(FTS_TRIGGER_SQL)
        if needs_create:
            connection.execute("INSERT INTO files_fts(files_fts) VALUES ('rebuild')")
        return True
    except sqlite3.OperationalError:
        return False
