import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import reset_initialized_databases
from app.main import app


def test_maintenance_module_runs(tmp_path, monkeypatch, capsys):
    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_AUDIT_RETENTION_DAYS", "1")

    from app import maintenance
    from app.db import init_db

    init_db()
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.execute(
        "INSERT INTO audit_logs (actor_id, action, entity_type, created_at)"
        " VALUES (NULL, 'stale', 'file', datetime('now', '-10 days'))"
    )
    connection.commit()
    connection.close()

    assert maintenance.main() == 0
    assert "已清理 1 条" in capsys.readouterr().out


def test_backup_creates_and_rotates_backups(tmp_path, monkeypatch, capsys):
    import zipfile

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app import backup
    from app.db import init_db

    init_db()
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "讲义.txt").write_text("内容", encoding="utf-8")

    destination = tmp_path / "backups"
    stamps = ("20260101-010101", "20260102-020202", "20260103-030303")
    results = []
    for stamp in stamps:
        result = backup.run(destination, keep=2, stamp=stamp)
        # 每份备份在生成时都必须存在且通过完整性校验（旧备份随后会被轮转清理）。
        assert result.database.is_file()
        assert backup.integrity_ok(result.database)
        results.append(result)

    assert results[0].removed == []
    # 第三次备份后，最旧的一组（数据库 + 上传归档）被清理。
    assert sorted(path.name for path in results[-1].removed) == [
        "coursebox-20260101-010101.db",
        "uploads-20260101-010101.zip",
    ]
    assert sorted(path.name for path in destination.iterdir()) == [
        "coursebox-20260102-020202.db",
        "coursebox-20260103-030303.db",
        "uploads-20260102-020202.zip",
        "uploads-20260103-030303.zip",
    ]

    with zipfile.ZipFile(destination / "uploads-20260103-030303.zip") as archive:
        assert archive.namelist() == ["讲义.txt"]

    # keep=0 表示全部保留。
    backup.run(destination, keep=0, stamp="20260104-040404")
    assert len(list(destination.iterdir())) == 6

    # 命令行入口：默认保留最近 1 组，并打印清理结果。
    assert backup.main(["--destination", str(destination), "--keep", "1"]) == 0
    output = capsys.readouterr().out
    assert "备份完成" in output
    assert "已清理" in output
    assert len(list(destination.iterdir())) == 2


def test_backup_skips_uploads_and_reports_missing_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app import backup
    from app.db import init_db

    init_db()
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "uploads" / "note.txt").write_text("hi", encoding="utf-8")

    destination = tmp_path / "backups"
    result = backup.run(
        destination, include_uploads=False, stamp="20260101-010101"
    )
    assert result.uploads is None
    assert [path.name for path in destination.iterdir()] == [
        "coursebox-20260101-010101.db"
    ]

    # 上传目录为空时跳过打包，不算失败。
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "empty-uploads"))
    assert backup.main(
        ["--destination", str(destination), "--keep", "0"]
    ) == 0
    assert "已跳过打包" in capsys.readouterr().out

    # 数据库不存在时返回 1 并给出原因。
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "missing.db"))
    assert backup.main(["--destination", str(destination)]) == 1
    assert "备份失败" in capsys.readouterr().err


def test_backup_script_entrypoint_is_importable():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "backup.py"
    spec = importlib.util.spec_from_file_location("coursebox_backup_script", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_health_probe_cleanup_removes_only_stale_probes(tmp_path, monkeypatch):
    import os
    import time as time_module

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))

    from app.db import cleanup_health_probes

    stale = uploads / ".health-stale"
    fresh = uploads / ".health-fresh"
    real_upload = uploads / "3f2a9c1b4d5e6f70"
    for path in (stale, fresh, real_upload):
        path.write_bytes(b"")

    two_hours_ago = time_module.time() - 2 * 60 * 60
    os.utime(stale, (two_hours_ago, two_hours_ago))

    assert cleanup_health_probes() == 1
    assert not stale.exists()
    # 一小时内的探针可能正属于正在进行的健康检查，不能删。
    assert fresh.exists()
    # 真正的上传文件用的是随机名、不以点开头，永远不碰。
    assert real_upload.exists()


def test_health_check_survives_probe_cleanup_failure(tmp_path, monkeypatch):
    from pathlib import Path

    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app.db import init_db

    init_db()

    # Windows 上杀毒软件会短暂锁住刚创建的文件，让删除抛 PermissionError。
    # 那只是清理失败，不该把实例判成不健康。
    def broken_unlink(self, *args, **kwargs):
        raise PermissionError(13, "文件被占用")

    monkeypatch.setattr(Path, "unlink", broken_unlink)

    body = client.get("/接口/健康").json()
    assert body["checks"]["uploads"]["status"] == "ok"


def _make_stale_probe(uploads: Path) -> Path:
    """在 uploads 里造一个「过期」的健康检查探针，供启动清理逻辑消费。"""
    uploads.mkdir(parents=True, exist_ok=True)
    probe = uploads / ".health-stale-probe"
    probe.write_bytes(b"")
    stale = time.time() - 7200
    os.utime(probe, (stale, stale))
    return probe


def test_importing_app_does_not_touch_uploads(tmp_path):
    """导入 app.main 只是加载代码，不该删 uploads 里的任何文件。

    回归背景：启动维护一度写在模块导入时执行，于是 pytest 收集测试（收集阶段就会
    import app.main）顺手把 uploads 里的残留探针删了；任何文档工具、linter 只要
    import 一次也会触发一遍破坏性维护。现在维护挪进了 lifespan。
    """
    uploads = tmp_path / "uploads"
    probe = _make_stale_probe(uploads)

    environment = dict(os.environ)
    environment["COURSEBOX_DB"] = str(tmp_path / "import.db")
    environment["COURSEBOX_UPLOAD_DIR"] = str(uploads)
    completed = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=Path(__file__).resolve().parent.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert probe.exists(), "导入 app.main 不应该删除 uploads 里的文件"


def test_startup_maintenance_runs_when_app_starts(tmp_path, monkeypatch):
    """真正启动应用（进入 lifespan）时才会执行启动维护。"""
    uploads = tmp_path / "uploads"
    probe = _make_stale_probe(uploads)
    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "startup.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(uploads))
    reset_initialized_databases()

    with TestClient(app):
        pass

    assert not probe.exists(), "应用启动（lifespan）应该清掉过期的健康检查探针"


def test_maintenance_purges_expired_sessions(tmp_path, monkeypatch, capsys):
    """过期会话由维护任务清理——读请求不再顺手写库，这里守住那条替代路径。"""

    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("COURSEBOX_UPLOAD_DIR", str(tmp_path / "uploads"))

    from app import maintenance
    from app.db import configure_connection, init_db

    init_db()

    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('u', 'x', 'viewer')"
    )
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at)"
        " VALUES (1, 'stale', datetime('now', '-1 day'))"
    )
    connection.commit()
    connection.close()

    assert maintenance.main() == 0
    assert "过期会话已清理 1 条" in capsys.readouterr().out


def test_checkpoint_wal_runs_without_error(tmp_path, monkeypatch):
    """维护任务会合并并截断 WAL，长跑实例的 -wal 文件不至于只涨不落。"""

    import sqlite3

    monkeypatch.setenv("COURSEBOX_DB", str(tmp_path / "test.db"))

    from app.db import checkpoint_wal, configure_connection, init_db

    init_db()
    connection = sqlite3.connect(tmp_path / "test.db")
    configure_connection(connection)
    connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('u', 'x', 'viewer')"
    )
    connection.commit()

    checkpoint_wal(connection)
    # 收尾后连接仍然可用，数据没有丢。
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM users WHERE username = 'u'"
        ).fetchone()[0]
        == 1
    )
    connection.close()
