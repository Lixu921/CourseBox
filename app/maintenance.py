"""数据库日常维护：清理过期审计日志与登录失败记录。

用法：`py -m app.maintenance`，可交给计划任务定期执行。
"""

import sqlite3

from app.config import database_path, get_settings
from app.db import (
    LOGIN_ATTEMPT_RETENTION_SECONDS,
    init_db,
    purge_audit_logs,
    purge_login_attempts,
)


def run() -> tuple[int, int]:
    settings = get_settings()
    connection = sqlite3.connect(database_path())
    try:
        init_db(connection)
        removed_audit = purge_audit_logs(connection, settings.audit_retention_days)
        removed_attempts = purge_login_attempts(
            connection, LOGIN_ATTEMPT_RETENTION_SECONDS
        )
    finally:
        connection.close()
    return removed_audit, removed_attempts


def main() -> int:
    removed_audit, removed_attempts = run()
    print(
        f"审计日志保留 {get_settings().audit_retention_days} 天，"
        f"已清理 {removed_audit} 条；"
        f"登录失败记录已清理 {removed_attempts} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
