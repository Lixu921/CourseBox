# CourseBox 第十一轮任务书：请求体、限流与内容校验加固

## 背景

延续「补齐已知缺口」的方向，本轮处理四件彼此相关的加固：分块传输绕过的请求体上限、
共用出口 IP 下按账号的写操作限流、伪装扩展名的可执行内容、以及几项安全响应头。

## 项目

| 编号 | 主题 | 现象 | 做法 |
| --- | --- | --- | --- |
| H1 | 分块请求体上限 | 只检查 `Content-Length`；分块传输没有该头，可绕过上传大小限制 | 新增 ASGI 中间件 `BodySizeLimitMiddleware`，包裹 `receive` 按实际字节数计数，超限抛 413 |
| H2 | 账户写操作限流 | 限流只按 IP，校园网共用出口时全站共享一个桶 | `current_user` 对写方法（POST/PUT/PATCH/DELETE）再按用户编号限流；只在已验证登录后进行，不额外查库 |
| H3 | 可执行内容校验 | 扩展名与 MIME 都能伪造（把 exe 改名 `.pdf`） | 上传落盘后检查文件头，命中 PE/ELF/Mach-O 魔数即 415 并删除文件 |
| H4 | 安全响应头 | 缺 `Permissions-Policy`、COOP、CORP | 全站兜底加上，仍用 `setdefault` 不覆盖更严格的设置 |

## 关键实现说明（H1）

分块上限走了两次弯路，记下结论以免重蹈：

1. **必须抛 FastAPI 自己的 `HTTPException`。** FastAPI 0.141 起 `fastapi.exceptions.HTTPException`
   是 `starlette.exceptions.HTTPException` 的子类；读取请求体的代码用 `except HTTPException`
   只认自己这一支，其它异常统一改写成 `400 There was an error parsing the body`。
2. **中间件必须是最内层用户中间件。** 若它和 FastAPI 之间还夹着 `@app.middleware` 生成的
   `BaseHTTPMiddleware`，从 `receive` 抛出的异常会被那一层吞掉。`add_middleware` 是「后注册在
   外层」，所以要在所有 `@app.middleware` 之前注册它。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- H1：分块传输（无 `Content-Length`）超限返回 413，且带安全头与 `X-Request-ID`。
- H2：账户写上限设 2 时，第三次写返回 429，读不受影响。
- H3：`MZ` 开头的 `.pdf` 返回 415 且不留孤儿文件；正常 PDF 可上传。
- H4：首页响应含三项新头。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/main.py` | `BodySizeLimitMiddleware`（最内层注册）；`SECURITY_HEADERS` 补三项 |
| `app/config.py` | `account_rate_limit_per_minute`（`COURSEBOX_ACCOUNT_RATE_LIMIT_PER_MINUTE`，默认 120） |
| `app/ratelimit.py` | `account_rate_limiter`，`reset_rate_limits` 一并重置 |
| `app/api/auth.py` | `current_user` 对写方法按账号限流 |
| `app/api/files.py` | `DANGEROUS_MAGIC` 文件头检测 |
| `tests/test_platform.py`、`tests/test_files.py` | 新增 4 条用例；`.env.example`、README 同步 |

验证：`ruff` 全绿，`pytest` 145 passed（第十轮 141 → 145）。
