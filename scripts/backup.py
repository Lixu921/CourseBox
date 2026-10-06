"""计划任务入口：等价于 `py -m app.backup`，便于用绝对路径注册计划任务。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.backup import main  # noqa: E402 - 需要先把项目根目录加入 sys.path

if __name__ == "__main__":
    raise SystemExit(main())
