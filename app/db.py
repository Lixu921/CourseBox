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


def ensure_fts(connection: sqlite3.Connection) -> bool:
    try:
        existing = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'files_fts'"
        ).fetchone()
        if not existing:
            connection.execute(
                """
                CREATE VIRTUAL TABLE files_fts USING fts5(
                    title, original_name, content='files', content_rowid='id'
                )
                """
            )
        connection.executescript(
            """
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
        )
        if not existing:
            connection.execute("INSERT INTO files_fts(files_fts) VALUES ('rebuild')")
        return True
    except sqlite3.OperationalError:
        return False
