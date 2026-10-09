# CourseBox 第二十三轮任务书：应急管理员找回

## 背景

托管平台（Render）生成的管理员密码找不到了，而应用侧又碰不到线上数据库，需要一条
「配置即生效」的找回通道：设置两个环境变量重启后，应用自动确保一个可用管理员。

## 设计

- 配置项（两个都设置且密码 ≥8 位才生效）：
  - `COURSEBOX_RECOVERY_ADMIN_USERNAME`
  - `COURSEBOX_RECOVERY_ADMIN_PASSWORD`
- 启动维护（`run_startup_maintenance`）中调用 `db.ensure_recovery_admin`：
  - 该用户名不存在 → 建为 `admin` + 启用；
  - 已存在 → 重置密码、设为 `admin` 且启用，并**作废其已有会话**（与重置密码策略一致）。
- 幂等：每次启动都会重设密码为环境变量值；**找回后应删掉这两个变量再部署**，避免长期留后门。
- 密码 <8 位直接忽略（`config` 里过滤），避免把后门配成弱口令。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 配置后启动：`owner` 能用配置密码登录、角色为 `admin`。
- 改密码再启动：旧密码 401、新密码可登录。
- 密码过短：不创建该账号。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/config.py` | `recovery_admin_username` / `recovery_admin_password`（含长度过滤） |
| `app/db.py` | `ensure_recovery_admin`（创建或重置 + 作废会话） |
| `app/main.py` | 启动维护中按配置调用 |
| `tests/test_platform.py` | 新增两条用例 |
| `.env.example`、`README.md`、`DEPLOY.md` | 用法与「用完删掉」提醒 |

验证：`ruff` 全绿，`pytest` 168 passed（第二十二轮 166 → 168）。
