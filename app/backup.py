"""数据库与上传目录的在线备份，支持保留最近 N 份并清理过期备份。

供计划任务调用：`py -m app.backup --destination backups --keep 7`。
"""

import argparse
import os
import re
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import PROJECT_ROOT, database_path, uploads_path

DEFAULT_DESTINATION_NAME = "backups"
DEFAULT_KEEP = 7
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
BACKUP_NAME_PATTERN = re.compile(r"^(coursebox|uploads)-(\d{8}-\d{6})\.(db|zip)$")


@dataclass
class BackupResult:
    """一次备份的产物：数据库文件、可选的上传归档、被清理的过期备份。"""

    database: Path
    uploads: Path | None
    removed: list[Path]


def default_destination() -> Path:
    configured = (os.getenv("COURSEBOX_BACKUP_DIR") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    return PROJECT_ROOT / DEFAULT_DESTINATION_NAME


def default_keep() -> int:
    raw = (os.getenv("COURSEBOX_BACKUP_KEEP") or "").strip()
    if not raw:
        return DEFAULT_KEEP
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_KEEP
    return value if value >= 0 else DEFAULT_KEEP


def timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime(TIMESTAMP_FORMAT)


def integrity_ok(path: Path) -> bool:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        connection.close()


def backup_database(source: Path, destination: Path, stamp: str) -> Path:
    """用 SQLite 在线备份接口导出数据库，校验通过后才改名为正式备份。"""

    target = destination / f"coursebox-{stamp}.db"
    temporary = target.with_suffix(".db.partial")
    source_connection = sqlite3.connect(source)
    target_connection = sqlite3.connect(temporary)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    if not integrity_ok(temporary):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"备份完整性校验失败：{temporary.name}")
    temporary.replace(target)
    return target


def archive_uploads(root: Path, destination: Path, stamp: str) -> Path | None:
    """把上传目录打包成 zip；目录不存在或没有文件时返回 None。"""

    if not root.is_dir():
        return None
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith(".coursebox-deleting-")
    ]
    if not files:
        return None
    target = destination / f"uploads-{stamp}.zip"
    temporary = target.with_suffix(".zip.partial")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(root).as_posix())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(target)
    return target


def prune_backups(destination: Path, keep: int) -> list[Path]:
    """按时间戳分组保留最近 keep 组（数据库 + 上传归档），其余删除。"""

    if keep <= 0:
        return []
    groups: dict[str, list[Path]] = {}
    for path in destination.iterdir():
        match = BACKUP_NAME_PATTERN.match(path.name)
        if match is None:
            continue
        groups.setdefault(match.group(2), []).append(path)
    stale = sorted(groups)[:-keep]
    removed: list[Path] = []
    for stamp in stale:
        for path in groups[stamp]:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


def clear_partial_files(destination: Path) -> None:
    """清掉上一次中断留下的 .partial 临时文件。"""

    for path in destination.glob("*.partial"):
        path.unlink(missing_ok=True)


def run(
    destination: Path | str | None = None,
    keep: int | None = None,
    include_uploads: bool = True,
    stamp: str | None = None,
) -> BackupResult:
    source = database_path()
    if not source.is_file():
        raise FileNotFoundError(f"数据库文件不存在：{source}")

    destination_path = Path(destination) if destination else default_destination()
    destination_path.mkdir(parents=True, exist_ok=True)
    clear_partial_files(destination_path)

    resolved_stamp = stamp or timestamp()
    database_backup = backup_database(source, destination_path, resolved_stamp)
    uploads_backup = (
        archive_uploads(uploads_path(), destination_path, resolved_stamp)
        if include_uploads
        else None
    )
    removed = prune_backups(
        destination_path, default_keep() if keep is None else keep
    )
    return BackupResult(
        database=database_backup, uploads=uploads_backup, removed=removed
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CourseBox 数据库与上传目录备份（支持保留最近 N 份）"
    )
    parser.add_argument(
        "--destination",
        default=str(default_destination()),
        help="备份输出目录，默认取 COURSEBOX_BACKUP_DIR 或项目下的 backups/",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=default_keep(),
        help="保留最近 N 份备份，0 表示全部保留",
    )
    parser.add_argument(
        "--no-uploads",
        action="store_true",
        help="只备份数据库，不打包上传目录",
    )
    args = parser.parse_args(argv)

    try:
        result = run(
            args.destination, keep=args.keep, include_uploads=not args.no_uploads
        )
    except (OSError, RuntimeError, sqlite3.Error, zipfile.BadZipFile) as error:
        print(f"备份失败：{error}", file=sys.stderr)
        return 1

    print(f"数据库备份：{result.database}")
    if result.uploads is not None:
        print(f"上传目录备份：{result.uploads}")
    elif not args.no_uploads:
        print("上传目录为空，已跳过打包。")
    if result.removed:
        print(f"已清理 {len(result.removed)} 个过期备份：")
        for path in result.removed:
            print(f"  - {path.name}")
    print("备份完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
