"""数据库日常维护：清理过期审计日志、登录失败记录、过期会话与回收站。

用法：`py -m app.maintenance`，可交给计划任务定期执行。
"""

import sqlite3

from app.config import database_path, get_settings
from app.db import (
    LOGIN_ATTEMPT_RETENTION_SECONDS,
    checkpoint_wal,
    init_db,
    purge_audit_logs,
    purge_deleted_files,
    purge_expired_sessions,
    purge_login_attempts,
)


def run() -> tuple[int, int, int, int]:
    settings = get_settings()
    connection = sqlite3.connect(database_path())
    try:
        init_db(connection)
        removed_audit = purge_audit_logs(connection, settings.audit_retention_days)
        removed_attempts = purge_login_attempts(
            connection, LOGIN_ATTEMPT_RETENTION_SECONDS
        )
        # 过期会话在这里清（启动维护也会做一遍），读请求不再顺手写库。
        removed_sessions = purge_expired_sessions(connection)
        # 回收站里的资料到期后在这里真正从磁盘删除。
        removed_trash = purge_deleted_files(connection, settings.trash_retention_days)
        # 最后合并并截断 WAL，避免长跑实例的 -wal 文件只涨不落。
        checkpoint_wal(connection)
    finally:
        connection.close()
    return removed_audit, removed_attempts, removed_sessions, removed_trash


def main() -> int:
    removed_audit, removed_attempts, removed_sessions, removed_trash = run()
    settings = get_settings()
    print(
        f"审计日志保留 {settings.audit_retention_days} 天，"
        f"已清理 {removed_audit} 条；"
        f"登录失败记录已清理 {removed_attempts} 条；"
        f"过期会话已清理 {removed_sessions} 条；"
        f"回收站保留 {settings.trash_retention_days} 天，"
        f"已彻底删除 {removed_trash} 条资料。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
