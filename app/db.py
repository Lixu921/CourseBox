import sqlite3
from typing import Generator

from app.config import database_path, uploads_path


# Kept as a compatibility alias for callers that imported the old constant.
UPLOADS_PATH = uploads_path()


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
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
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
            """
        )
        ensure_fts(connection)
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
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


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
