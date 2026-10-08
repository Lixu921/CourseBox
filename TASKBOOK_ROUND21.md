# CourseBox 第二十一轮任务书：自助注册（一个 IP 一个）

## 背景

此前账户只能由管理员创建。本轮开放自助注册：注册即登录，**一个来源 IP 只能注册一个账户**。

## 明确的前提

「一个 IP 一个」是**软限制**：校园网等共用出口 IP 下整片网络只能注册一个；换 IP（手机流量/代理）
即可绕过。它防手滑，不防刷；真正的兜底是接口限流与管理员治理。README「已知局限」写清。

## 设计

- `users` 加 `registered_ip TEXT`（历史/管理员建的账户为空），结构版本升到 v10。
- 配置：
  - `COURSEBOX_ALLOW_REGISTRATION`（默认 `true`）：关闭后注册接口返回 403。
  - `COURSEBOX_REGISTER_ROLE`（默认 `uploader`）：只允许 `uploader`/`viewer`，非法值（含
    `admin`）一律回退默认——**自助注册永远拿不到管理员**。
- 接口 `POST /接口/注册`（别名 `/api/register`），body `{username, password}`：
  - 关闭注册 → 403；同 IP 已注册 → 409；用户名重复 → 409。
  - 成功：建账户（`registered_ip` = 解析后的客户端 IP）、**直接建会话并下发 Cookie**（注册即登录）。
- 审计新增动作 `register`（写入、筛选下拉、CSV 标签）。
- 前端：登录旁加「注册」按钮与注册面板（两页共享），注册成功刷新登录态。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 注册成功返回 201，角色为 `uploader`，随后 `/接口/当前用户` 已是该用户（自动登录）。
- 同来源 IP 第二次注册 409。
- 用户名 < 3、密码 < 8 → 422；同名（不同 IP）→ 409。
- `COURSEBOX_ALLOW_REGISTRATION=false` → 403；`COURSEBOX_REGISTER_ROLE=admin` → 实际仍是 `uploader`。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/config.py` | `allow_registration` / `register_role`（含角色白名单回退） |
| `app/db.py` | `users.registered_ip` + 迁移；`SCHEMA_VERSION = 10` |
| `app/schemas.py` | `RegisterRequest` |
| `app/api/auth.py` | `POST /接口/注册`：开关/每 IP 一个/用户名唯一/自动登录 |
| `app/api/audit.py`、`static/index.html` | 审计动作 `register` 与筛选项 |
| `static/index.html`、`course.html`、`app.js`、`app-3.js` | 注册按钮与面板、自动登录刷新 |
| `tests/test_register.py` | 新增五条用例 |
| `.env.example`、`README.md` | 配置与「已知局限」同步 |

验证：`ruff` 全绿，`pytest` 166 passed（第二十轮 161 → 166）。
