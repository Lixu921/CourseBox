# CourseBox 第七轮任务书：复审加固

## 背景

第六轮之后对代码做了一次以「真实服务行为」为准的复审，逐条复现后找出若干**可直接观测**的
缺陷与运维缺口。与第六轮不同，这一轮不新增面向用户的功能，只做加固与纠错：修掉会白屏的
接口文档、会泄露内部信息的健康检查、在反向代理后失效的限流与登录锁定、解析前不设防的
请求体，以及几处部署/工程配置。

复审时仓库正被另一进程并行提交（新增了「坏 Cookie 不再在读路径写库」「库结构版本记进
`PRAGMA user_version`」「文档漂移修正」三处改动）。本任务书只覆盖**当前 HEAD 仍未解决**
的问题，已修复项不再重复。

## 执行约定

- 只改动本仓库（`CourseBox/`）内的文件。
- 每一项独立实现、独立验收；提交信息写清「做了什么 + 为什么」。
- 每次提交前 `py -m ruff check .` 与 `py -m pytest` 必须全绿（看到 `N passed` 汇总行）。
- 不引入 Node/npm、外部 CDN 作为运行时依赖（接口文档例外：Swagger 由 FastAPI 自带，
  允许其 CDN 脚本，见 R1）。

## 问题清单

| 编号 | 优先级 | 主题 | 现象 / 风险 |
| --- | --- | --- | --- |
| R1 | 高 | 接口文档被自身 CSP 打挂 | `/接口文档`、`/接口说明` 是 FastAPI 默认 Swagger/ReDoc，引 CDN 脚本且含内联 `<script>`；全站 `PAGE_CSP` 是 `script-src 'self'`，两者都被拦，页面白屏 |
| R2 | 高 | 健康检查泄露内部错误 | `/接口/健康` 公开无鉴权，失败时把 `str(OSError/SQLite)` 原样放进响应，可能带出数据库/上传目录路径 |
| R3 | 高 | 代理后限流与登录锁定失效 | 限流键与登录锁定键都用 `request.client.host`。uvicorn 默认只信任 `127.0.0.1` 转发头，在 Render 等代理后拿到的是代理 IP：全站共用一个限流桶；对某账号失败 5 次即可把该账号对所有人锁死 |
| R4 | 高 | 请求体在解析后才限制 | Starlette 会把整个 multipart body 落盘后才进入端点，端点的 413 来得太晚，可被超大上传消耗磁盘/带宽 |
| R5 | 中 | 排序字段无索引 | 搜索/列表按 `upload_time`、`size` 排序，无对应索引 |
| R6 | 中 | 部署健康检查路径 | `render.yaml` 用 `healthCheckPath: /`，只测 HTML，DB 挂了平台仍判健康 |
| R7 | 中 | 前端写死 20 MB | `static/app.js` 的 `MAX_FILE_SIZE` 与 `course.html` 文案写死 20 MB，后端上限可配，二者会不一致 |
| R8 | 中 | 依赖未分层 | `requirements.txt` 把 pytest/httpx 等测试依赖装进生产镜像 |
| R9 | 中 | 容器以 root 运行 | Dockerfile 无 `USER` |
| R10 | 中 | 恢复不含上传文件 | `restore.ps1` 只还原数据库，备份里的 uploads zip 没有恢复入口 |
| R11 | 低 | CI 版本缺口 | 本地在 3.14 验证，CI 矩阵只到 3.13 |
| R12 | 低 | 文档同步 | 新增配置与用法需写进 README / `.env.example` |

## 各项设计

### R1 接口文档与 CSP

- 新增文档专用 CSP `DOCS_CSP`：允许 `cdn.jsdelivr.net` 的脚本/样式与 `'unsafe-inline'`
  （Swagger/ReDoc 依赖内联初始化脚本），其余保持收紧。
- `security_headers_middleware` 对 `/接口文档`、`/接口说明` 前缀改用 `DOCS_CSP`，其余 HTML
  仍用 `PAGE_CSP`。
- 新增开关 `COURSEBOX_ENABLE_DOCS`（默认 `true`）。关闭时 `docs_url`/`redoc_url`/
  `openapi_url` 全部为 `None`，生产可按需收敛。

### R2 健康检查不泄露细节

- 三个检查函数失败时只返回**通用中文原因**，真实异常写进结构化日志（`event=health_check`）。
- 保持 `/接口/健康` 的 `checks` 形状与 503 语义不变。

### R3 代理下的客户端识别

- 新增配置 `COURSEBOX_TRUST_PROXY`（默认 `false`）。
- 新增 `app.ratelimit.client_ip(request)`：开启信任代理时取 `X-Forwarded-For` 最左段作为
  客户端 IP，否则用 `request.client.host`。限流键与登录锁定键都改走它。
- `render.yaml` 显式设置 `COURSEBOX_TRUST_PROXY=true`。
- 说明：只信任一层代理的最左段；不开启时行为与现在完全一致，避免直连场景被伪造头绕过限流。

### R4 请求体上限前置

- 新增配置 `COURSEBOX_MAX_REQUEST_BYTES`，默认 `max_file_size + 1 MiB`（multipart 边界与
  表单字段的余量）。
- 新增 `request_size_limit_middleware`：带 `Content-Length` 且超过上限时，**在进入端点前**
  直接返回 413（统一错误结构，带 `request_id` 与安全头）。
- 局限：依赖 `Content-Length`；分块传输（无该头）仍需反向代理兜底，写入 README「已知局限」。

### R5 排序索引

- `init_db` 增加 `idx_files_upload_time`、`idx_files_size`；`SCHEMA_VERSION` 记为 v4。

### R6 / R7 / R8 / R9 / R10 / R11 / R12

- R6：`render.yaml` 的 `healthCheckPath` 改为 `/api/health`（新增该 ASCII 别名，避免中文
  路径在不同平台上的编码问题）。
- R7：`app.js` 用 `let maxFileSize` 并从课程配额响应的 `max_file_size` 更新；提示文案改用
  `formatFileSize(maxFileSize)`。`course.html` 的静态提示改为占位，由脚本填充。
- R8：`requirements.txt` 仅保留运行时依赖；新增 `requirements-dev.txt`；CI 安装 dev 文件。
- R9：Dockerfile 建非 root 用户并 `USER`。
- R10：`restore.ps1` 增加可选 `-Uploads <zip>`，校验后解包到上传目录。
- R11：CI 矩阵加入 `3.14`，覆盖率门槛移到 3.14 那条腿。
- R12：README / `.env.example` 同步新增配置与用法，「已知局限」补充分块上传一条。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- R1：`GET /接口文档` 的 CSP 含 `cdn.jsdelivr.net` 且页面含 swagger bundle；`PAGE_CSP` 不变。
- R2：上传目录不可用时，`checks.uploads.message` 不含该路径字符串。
- R3：信任代理时，不同 `X-Forwarded-For` 各自计数；不信任时忽略该头。
- R4：`Content-Length` 超限的请求在端点前拿到 413，且响应头带 `X-Request-ID`。
- R5：新库存在两个排序索引。
- 其余：静态检查与全量测试通过，用例数不少于改动前。

## 完成情况

| 编号 | 结果 | 落点 |
| --- | --- | --- |
| R1 | 完成 | `app/main.py`：`DOCS_CSP` + `DOCS_PATH_PREFIXES`，`security_headers_middleware` 按前缀切换；`COURSEBOX_ENABLE_DOCS` 控制文档开关 |
| R2 | 完成 | `app/main.py`：三个健康检查失败时返回通用中文原因，异常写日志 |
| R3 | 完成 | `app/config.py` 新增 `trust_proxy`；`app.ratelimit.client_ip`；`app/api/auth.py` 登录锁定改用之；`render.yaml` 设 `COURSEBOX_TRUST_PROXY=true` |
| R4 | 完成 | `app/config.py` 新增 `max_request_bytes`（默认单文件上限 + 1 MiB）；`app/main.py` 新增 `request_size_limit_middleware` |
| R5 | 完成 | `app/db.py` 新增两个索引并记 `SCHEMA_VERSION = 4` |
| R6 | 完成 | `app/main.py` 新增 `/api/health` 别名；`render.yaml` 改用它 |
| R7 | 完成 | `static/app.js` 的 `maxFileSize` 从配额响应更新；`static/course.html` 占位文案 |
| R8 | 完成 | `requirements.txt` 仅运行时；新增 `requirements-dev.txt`；CI 改装 dev |
| R9 | 完成 | `Dockerfile` 建非 root 用户并 `USER` |
| R10 | 完成 | `scripts/restore.ps1` 新增 `-Uploads` |
| R11 | 完成 | CI 矩阵加 3.14，覆盖率门槛移到 3.14 |
| R12 | 完成 | `README.md`、`.env.example` 同步；「已知局限」补三条 |

验证：

```powershell
py -m ruff check .   # All checks passed
py -m pytest         # 133 passed
```

用例数 124 → 133（新增接口文档 CSP、文档开关、健康不泄露、健康别名、请求体上限、
排序索引、代理来源识别两条、代理下登录锁定）。`render.yaml` / `Dockerfile` /
`restore.ps1` 为脚本与配置，未纳入 pytest。
