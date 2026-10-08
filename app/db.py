import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Generator
from pathlib import Path

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

# 库结构版本，记在 SQLite 自带的 PRAGMA user_version 里。任何改表动作（加列、加索引、
# 改约束）都要 +1，并在 migrate_schema 里登记对应步骤。有了它，拿到一个库文件就能直接
# 问出「升到第几版」，不用靠 PRAGMA table_info 一条条猜。
#   v1 初始表结构（courses / files / users / sessions / audit_logs / login_attempts）
#   v2 files 补 mime_type / sha256 / status / uploaded_by
#   v3 files 补 deleted_at / deleted_by（回收站），users 补 is_active
#   v4 files 补 upload_time / size 排序索引
#   v5 courses / files 补 version（编辑乐观锁）
#   v6 courses 补 tags（逗号分隔的分类标签）
#   v7 新增 share_links（只读分享链接）
SCHEMA_VERSION = 7


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
                semester TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                tags TEXT
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
                version INTEGER NOT NULL DEFAULT 1,
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

            CREATE TABLE IF NOT EXISTS share_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                course_id INTEGER NOT NULL,
                created_by INTEGER,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            );
            """
        )
        migrate_schema(connection)
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_courses_name ON courses(name);
            CREATE INDEX IF NOT EXISTS idx_files_course_id ON files(course_id);
            CREATE INDEX IF NOT EXISTS idx_files_title ON files(title);
            CREATE INDEX IF NOT EXISTS idx_files_original_name ON files(original_name);
            CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
            CREATE INDEX IF NOT EXISTS idx_files_uploaded_by ON files(uploaded_by);
            CREATE INDEX IF NOT EXISTS idx_files_deleted_at ON files(deleted_at);
            -- 列表与搜索默认按上传时间、大小排序，加索引避免全表 filesort。
            CREATE INDEX IF NOT EXISTS idx_files_upload_time ON files(upload_time);
            CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_login_attempts_locked_until
                ON login_attempts(locked_until);
            """
        )
        # sha256 唯一索引由这个函数负责建：它的 WHERE 条件含 deleted_at，
        # 老库里的旧索引需要重建，不能交给上面的 IF NOT EXISTS 一句话带过。
        ensure_files_sha256_index(connection)
        ensure_fts(connection)
        ensure_bootstrap_admin(connection)
        connection.commit()
    finally:
        if close_connection:
            connection.close()


# 已经建过表的数据库文件（按绝对路径记）。init_db 里全是 CREATE TABLE/INDEX 与
# PRAGMA journal_mode=WAL，在新建连接上跑一次要 100-230ms；每个请求都跑一遍会让
# 单次请求从 2ms 涨到 200ms 以上，所以只在进程首次打开该库时做一次。
_initialized_paths: set[str] = set()
_init_lock = threading.Lock()


def ensure_database(connection: sqlite3.Connection, path: Path) -> None:
    """该数据库文件在本进程内首次使用时才做结构初始化，之后直接跳过。

    注意：结构可以跳过，但连接级设置（row_factory、PRAGMA）每个新连接都必须重设，
    否则取出来的行是普通 tuple，按列名取值会直接报错。
    """

    key = str(path.resolve())
    with _init_lock:
        if key in _initialized_paths:
            configure_connection(connection)
            return
        init_db(connection)
        _initialized_paths.add(key)


def reset_initialized_databases() -> None:
    """清掉初始化缓存。测试换了数据库文件后必须调用，否则新库不会被建表。"""

    with _init_lock:
        _initialized_paths.clear()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        ensure_database(connection, path)
        yield connection
    finally:
        connection.close()


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    # journal_mode 是数据库文件的持久属性，设一次就一直有效；而执行这条赋值语句本身
    # 要重新协商锁，Windows 上实测约 100ms。所以只在还不是 WAL 时才切换。
    current = connection.execute("PRAGMA journal_mode").fetchone()[0]
    if str(current).lower() != "wal":
        connection.execute("PRAGMA journal_mode = WAL")


def migrate_schema(connection: sqlite3.Connection) -> None:
    """把老库补齐到 SCHEMA_VERSION，并把版本号写回 PRAGMA user_version。

    各步迁移本身是幂等的（靠 PRAGMA table_info 判断列是否已存在），所以中途失败、
    下次重跑也安全；这里额外做的事只是让「库升到第几版」变得可查。
    新库由上面的 CREATE TABLE 一次建到最新结构，跑到这里时迁移全是空操作，只写版本号。
    """

    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    migrate_files_table(connection)
    migrate_users_table(connection)
    migrate_courses_table(connection)
    # PRAGMA 不支持占位符参数，只能拼进语句；值来自本模块的整数常量，不含外部输入。
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")  # noqa: S608


def migrate_files_table(connection: sqlite3.Connection) -> None:
    """给老库的 files 表补上后加的列，历史行取各列的默认值。"""

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(files)").fetchall()
    }
    migrations = {
        "mime_type": "ALTER TABLE files ADD COLUMN mime_type TEXT",
        "sha256": "ALTER TABLE files ADD COLUMN sha256 TEXT",
        "status": "ALTER TABLE files ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
        "uploaded_by": "ALTER TABLE files ADD COLUMN uploaded_by INTEGER",
        # 回收站：删除资料只打标记，磁盘文件先留着，超期才真正清理。
        "deleted_at": "ALTER TABLE files ADD COLUMN deleted_at TEXT",
        "deleted_by": "ALTER TABLE files ADD COLUMN deleted_by INTEGER",
        # 编辑乐观锁：每次修改 +1，客户端带上自己看到的版本号，冲突就报 409。
        "version": "ALTER TABLE files ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


def migrate_courses_table(connection: sqlite3.Connection) -> None:
    """老库的 courses 补上 version（乐观锁）与 tags（标签）。"""

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(courses)").fetchall()
    }
    if "version" not in columns:
        connection.execute(
            "ALTER TABLE courses ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        )
    if "tags" not in columns:
        connection.execute("ALTER TABLE courses ADD COLUMN tags TEXT")


def migrate_users_table(connection: sqlite3.Connection) -> None:
    """老库补上启用状态列，历史账号默认保持可用。"""

    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
    if "is_active" not in columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )


SHA256_INDEX_NAME = "idx_files_course_sha256"
# 同一课程内按内容哈希去重。必须排除已软删除的行，否则一份资料被删进回收站后，
# 它仍然占着唯一约束，同一份文件就再也传不进这门课了。
SHA256_INDEX_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {SHA256_INDEX_NAME} "
    "ON files(course_id, sha256) WHERE sha256 IS NOT NULL AND deleted_at IS NULL"
)


def ensure_files_sha256_index(connection: sqlite3.Connection) -> None:
    """建立（或把老库里的旧版）内容去重唯一索引升级成排除已删除行的版本。"""

    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (SHA256_INDEX_NAME,),
    ).fetchone()
    existing = row["sql"] if row is not None else None
    if existing is not None:
        if "deleted_at" in existing.lower():
            return
        # 老索引没有 deleted_at 条件。它此前一直生效，所以未删除行之间不可能有重复，
        # 重建不会因为数据冲突而失败。
        connection.execute(f"DROP INDEX {SHA256_INDEX_NAME}")
    connection.execute(SHA256_INDEX_SQL)


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


def purge_expired_sessions(connection: sqlite3.Connection) -> int:
    """删掉已过期的会话，返回清理条数。

    只放在维护任务里执行（启动维护与 `py -m app.maintenance`）。以前这步挂在
    find_session_user 上，任何带无效 Cookie 的请求都会顺手删一遍会话表——无效
    Cookie 是外部随便构造的，等于把一个写操作暴露给了读路径。
    """

    cursor = connection.execute(
        "DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP"
    )
    connection.commit()
    return cursor.rowcount or 0


def checkpoint_wal(connection: sqlite3.Connection) -> None:
    """把 WAL 日志合并回主库并截断，避免长跑实例下 -wal 文件只涨不落。

    TRUNCATE 模式在有其他读者时会退化成不截断而不是报错，因此放在维护任务里定期
    执行即可，不追求每次都能截断。
    """

    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
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


def purge_deleted_files(connection: sqlite3.Connection, retention_days: int) -> int:
    """把回收站里超过保留期的资料真正删掉（含磁盘文件），返回清理条数。

    复用删除流程里的暂存机制：先把磁盘文件改名移开、写日志，数据库删除提交成功
    后才真正 unlink；中途失败会回滚并把文件改回来，不会出现「记录没了文件还在」
    或「文件没了记录还在」。
    """

    if retention_days <= 0:
        return 0
    rows = connection.execute(
        """
        SELECT id, filename FROM files
        WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', ?)
        """,
        (f"-{retention_days} days",),
    ).fetchall()
    if not rows:
        return 0

    staged = stage_stored_files(rows, connection)
    placeholders = ", ".join("?" for _ in rows)
    try:
        connection.execute(
            f"DELETE FROM files WHERE id IN ({placeholders})",  # noqa: S608 - 占位符数量由内部查询结果决定
            [row["id"] for row in rows],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        restore_staged_files(staged, connection)
        raise
    discard_staged_files(staged, connection)
    return len(rows)


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
            f"DELETE FROM file_deletion_journal WHERE staged_name IN ({placeholders})",  # noqa: S608 - 占位符数量由内部列表决定
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


# 健康检查的探针文件名前缀。正常情况下建完立刻删掉，只有在删除被占用而失败时
# 才会残留（Windows 上杀毒软件/同步盘偶尔会短暂锁住刚创建的文件）。
HEALTH_PROBE_PREFIX = ".health-"
# 只清理一小时前的探针，避免把正在进行的健康检查自己的文件删掉。
HEALTH_PROBE_MAX_AGE_SECONDS = 60 * 60


def cleanup_health_probes(
    max_age_seconds: int = HEALTH_PROBE_MAX_AGE_SECONDS,
) -> int:
    """清掉健康检查遗留的探针文件，返回删除个数。

    只匹配「以 .health- 开头 + 普通文件 + 修改时间超过一小时」这三条同时成立
    的条目。上传落盘用的是随机文件名、不以点开头，所以不会误删用户资料。
    """

    directory = uploads_path()
    if not directory.is_dir():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    try:
        entries = list(directory.iterdir())
    except OSError as error:
        logger.warning(
            "health probe scan failed: %s",
            error,
            extra={"event": "file_cleanup"},
        )
        return 0
    for entry in entries:
        if not entry.name.startswith(HEALTH_PROBE_PREFIX):
            continue
        try:
            if not entry.is_file() or entry.stat().st_mtime > cutoff:
                continue
            entry.unlink()
            removed += 1
        except OSError as error:
            logger.warning(
                "health probe cleanup failed: %s",
                error,
                extra={"event": "file_cleanup"},
            )
    return removed


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
