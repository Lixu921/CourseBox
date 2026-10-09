# 课盒子

课盒子是一个基于 FastAPI 和 SQLite 的课程资料共享小站。用户可以按课程浏览资料、上传文件、下载资料，也可以按课程名、资料标题或原文件名搜索。

## 功能

- 首页展示课程列表，支持按课程、文件类型、上传时间范围筛选，并按最新、最早、标题或大小排序
- 首页展示「热门资料」（按下载次数）与「最新资料」
- 搜索结果中的关键词在标题、文件名和课程名上高亮显示
- 课程详情页展示资料并支持上传，上传区支持拖拽与多选，逐个显示进度和结果
- PDF、图片和纯文本资料可以在弹层中在线预览，其余类型仍走下载
- 上传文件大小限制为 20 MB（另有单课程、站点总量与磁盘剩余空间三重配额保护）
- 使用随机文件名保存上传内容，保留原始文件名用于展示和下载
- 直接下载课程资料
- 搜索课程名、资料标题和原文件名；中文子串通过 FTS5 trigram 索引命中
- 课程支持分类标签，课程列表可按标签筛选，标签也参与课程关键词搜索
- 管理员可为课程生成带有效期的只读分享链接，分享页展示该课程已通过的资料
- 管理员可在「站点概览」查看课程/资料/用户数量与存储用量；登录后可在「登录设备」查看并退出其它会话
- 资料支持评论：登录后可发表，作者与管理员可删除（前端每隔几秒轮询刷新）
- 支持自助注册（一个来源 IP 限注册一个账户），注册即登录
- 三种角色：管理员可管理课程与用户，上传者提交的资料需审核，浏览者只读
- 「我的上传」列出自己提交的资料及其审核状态，待审核的可撤回
- 前端提供加载、空结果和请求失败提示

## 权限与账户

首次启动会创建 `COURSEBOX_ADMIN_USERNAME` 指定的管理员账户。登录后可在首页的「用户管理」面板查看用户列表、创建账户、调整角色、停用/启用账户和重置密码；系统始终保留至少一个启用的管理员，且不允许修改或停用当前登录账户。

默认开放**自助注册**（`/接口/注册`）：注册即登录，角色为 `uploader`（可用 `COURSEBOX_REGISTER_ROLE` 改成 `viewer`，绝不会是 `admin`）。**一个来源 IP 只能注册一个账户**（软限制，见「已知局限」），可用 `COURSEBOX_ALLOW_REGISTRATION=false` 关闭注册。

非管理员上传的资料默认为待审核状态，管理员在课程页或资料列表上执行通过/拒绝。停用账户会立即失效其已登录会话，重置密码同样会作废该用户的全部会话。

## 目录

```text
CourseBox/
├─ app/
│  ├─ api/
│  │  ├─ audit.py       # 审计日志查询与导出（管理员）
│  │  ├─ auth.py        # 登录、当前用户、退出、自助改密
│  │  ├─ common.py      # 分页、LIKE 转义、日期解析等公共工具
│  │  ├─ comments.py    # 资料评论
│  │  ├─ courses.py     # 课程接口
│  │  ├─ files.py       # 资料上传、下载、预览、搜索、回收站、打包与导出
│  │  ├─ insights.py    # 热门 / 最新资料与站点概览
│  │  ├─ share.py       # 课程只读分享链接
│  │  └─ users.py       # 管理员用户管理
│  ├─ auth.py           # 口令哈希与会话令牌
│  ├─ backup.py         # 数据库与上传目录备份、轮转
│  ├─ config.py         # 环境变量与运行配置
│  ├─ csv_export.py     # CSV 渲染（BOM、CRLF、公式注入中和、中文文件名）
│  ├─ db.py             # SQLite 连接、建表、迁移与清理
│  ├─ main.py           # FastAPI 应用、页面路由、中间件与接口文档本地化
│  ├─ maintenance.py    # 保留策略清理（审计日志、登录记录、过期会话、回收站）
│  ├─ ratelimit.py      # 进程内限流
│  └─ schemas.py        # 请求、响应模型
├─ static/
│  ├─ index.html        # 首页
│  ├─ course.html       # 课程详情页
│  ├─ error.html       # 浏览器访问出错时的中文错误页
│  ├─ share.html        # 只读分享页
│  ├─ app.js            # 原生 JavaScript 交互（第一段）
│  ├─ app-2.js          # 原生 JavaScript 交互（第二段）
│  ├─ app-3.js          # 原生 JavaScript 交互（第三段）
│  ├─ share.js          # 分享页脚本
│  ├─ style.css         # 页面样式
│  └─ favicon.svg       # 网站图标
├─ tests/               # 按域拆分，公共夹具在 conftest.py
│  ├─ conftest.py       # TestClient 工厂与登录辅助
│  ├─ test_platform.py  # 健康检查、页面路由、错误响应、限流、安全响应头
│  ├─ test_courses.py   # 课程增删改查、分页、配额
│  ├─ test_files.py     # 上传、下载、预览、重复检测与配额
│  ├─ test_search.py    # 搜索、筛选、排序与命中字段
│  ├─ test_accounts.py  # 登录、会话、角色与自助改密
│  ├─ test_trash.py     # 回收站（单条与批量）
│  ├─ test_archive.py   # 打包下载
│  ├─ test_batch.py     # 用户与资料批量操作
│  ├─ test_audit.py     # 审计日志
│  ├─ test_export.py    # CSV 导出
│  ├─ test_ops.py       # 维护、备份、健康探针与启动维护
│  └─ test_frontend_contract.py  # 前端 fetch 与后端路由一致性
├─ scripts/
│  ├─ start.ps1         # Windows 启动脚本
│  ├─ backup.ps1        # 备份脚本（调用 scripts/backup.py）
│  ├─ backup.py         # 计划任务入口，等价于 py -m app.backup
│  ├─ db_check.py       # 备份完整性校验
│  ├─ restore.ps1       # 备份校验和恢复
│  └─ smoke.py          # 真实服务的端到端冒烟（CI 用）
├─ .github/workflows/   # GitHub Actions：ruff 检查 + pytest（3.14 腿带覆盖率门槛）
├─ .dockerignore        # 容器构建忽略清单
├─ .env.example         # 环境配置示例
├─ .gitignore           # 排除 data/、uploads/、backups/ 等
├─ DEPLOY.md            # 部署说明
├─ Dockerfile           # 容器镜像构建
├─ docker-compose.yml   # 带持久化卷的本地/单机编排
├─ LICENSE              # 开源许可
├─ README.md            # 项目说明（本文件）
├─ TASKBOOK.md          # 开工时的原始任务书（正文属历史，见其中的「现状注记」）
├─ TASKBOOK_OPTIMIZATION.md  # 各轮优化的完成记录
├─ TASKBOOK_ROUND7.md   # 第七轮（复审加固）任务书
├─ TASKBOOK_ROUND8.md   # 第八轮（运行期整洁）任务书
├─ TASKBOOK_ROUND9.md   # 第九轮（健康检查缓存与审计游标）任务书
├─ TASKBOOK_ROUND10.md  # 第十轮（编辑乐观锁）任务书
├─ TASKBOOK_ROUND11.md  # 第十一轮（请求体/限流/内容校验加固）任务书
├─ TASKBOOK_ROUND12.md  # 第十二轮（CI 冒烟、依赖审计、compose）任务书
├─ TASKBOOK_ROUND13.md  # 第十三轮（按上传者配额）任务书
├─ TASKBOOK_ROUND14.md  # 第十四轮（课程标签）任务书
├─ TASKBOOK_ROUND15.md  # 第十五轮（只读分享链接）任务书
├─ TASKBOOK_ROUND16.md  # 第十六轮（OpenAPI 本地化重写）任务书
├─ TASKBOOK_ROUND17.md  # 第十七轮（前端经典脚本拆分）任务书
├─ TASKBOOK_ROUND18.md  # 第十八轮（下载计数/热门、站点概览、登录设备）任务书
├─ TASKBOOK_ROUND19.md  # 第十九轮（并发一致性修复）任务书
├─ TASKBOOK_ROUND20.md  # 第二十轮（资料评论）任务书
├─ TASKBOOK_ROUND21.md  # 第二十一轮（自助注册）任务书
├─ pyproject.toml       # 项目元数据、pytest、Ruff 与覆盖率配置
├─ render.yaml          # Render 部署配置
├─ requirements.txt     # 运行时依赖
├─ requirements-dev.txt # 测试与静态检查依赖（-r requirements.txt）
├─ data/                # 本地 SQLite 数据库，不提交到 Git
├─ uploads/             # 上传文件，不提交到 Git
└─ backups/             # 备份输出目录，不提交到 Git
```

## 环境要求

- Python 3.11 及以上（本地在 3.14 上验证，CI 覆盖 3.11 / 3.12 / 3.13 / 3.14）
- Windows 环境建议使用 `py` 命令

## 安装依赖

只运行服务：

```powershell
py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

要跑测试和静态检查，装开发依赖（它已经包含运行时依赖）：

```powershell
py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-dev.txt
```

如果本机代理导致安装失败，可以在该命令前临时设置 `NO_PROXY=*`，不要修改系统代理配置。

## 配置项目

复制 `.env.example` 为 `.env`，再按部署环境调整值。应用启动时会读取项目根目录 `.env`，但不会覆盖已有系统环境变量；生产环境可直接由进程管理器设置变量：

```powershell
$env:COURSEBOX_DB = "data/coursebox.db"
$env:COURSEBOX_UPLOAD_DIR = "uploads"
$env:COURSEBOX_ADMIN_PASSWORD = "请替换为至少 8 位密码"
```

支持的主要配置包括数据库路径、上传目录、单文件大小、请求体上限、健康检查缓存秒数、账户写操作限流、上传配额（单课程/站点/单用户）、允许扩展名、最低可用磁盘空间、日志级别、监听地址和端口。前面有反向代理时设 `COURSEBOX_TRUST_PROXY=true`，让限流与登录锁定按 `X-Forwarded-For` 区分访客；生产环境可用 `COURSEBOX_ENABLE_DOCS=false` 关闭接口文档。完整列表见 `.env.example`。

## 启动项目

```powershell
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows 也可以使用启动脚本：

```powershell
.\scripts\start.ps1 -Port 8000
```

如果 Windows 的 `py` 或 `python` 命令被系统执行别名拦截，可先指定解释器：`$env:COURSEBOX_PYTHON = "C:\Python314\python.exe"`。

在线访问（点开就能用，无需部署）：

- 应用首页（课盒子）：<https://coursebox.onrender.com/>
- 在线接口文档：<https://coursebox.onrender.com/接口文档>

> 免费实例闲置约 15 分钟后会自动休眠，长时间没人访问时首次打开需要等待约 30-60 秒，属正常现象。仓库自带 `.github/workflows/keepalive.yml` 每 5 分钟访问一次健康接口以减少冷启动（也可另配 UptimeRobot）；免费盘的数据库与上传仍是临时的，持久化做法见 [DEPLOY.md](DEPLOY.md)。

本地启动服务后，在运行服务的电脑上可以访问 `http://127.0.0.1:8000/`；同一局域网的同学请访问运行服务电脑的局域网 IPv4 地址，例如 `http://192.168.1.23:8000/`。启动脚本会打印可分享的局域网地址。若同学仍然无法访问，请确认双方连接的是同一个 Wi-Fi/局域网，并在 Windows 防火墙中允许 Python/Uvicorn 接受专用网络的入站连接；校园网可能会阻止设备之间互相访问。

如果需要重新部署或另建一份实例，可以[在 Render 上创建服务](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FLixu921%2FCourseBox)，或先阅读[部署说明](DEPLOY.md)。注意：这个链接是**部署入口**，打开后会进入 Render 控制台（用来创建/更新服务），并不是课盒子本身；部署完成后请使用 Render 分配的 `onrender.com` 地址访问应用。

网页和接口统一使用中文路径：课程页为 `/课程`，样式和脚本为 `/资源/样式.css`、`/资源/脚本.js`（页面引用时会带上 `?v=<内容哈希>`，内容一变版本号就变，可以放心长期缓存），网站图标为 `/资源/图标.svg`，课程接口为 `/接口/课程`，资料接口为 `/接口/课程/{编号}/资料`，下载地址为 `/接口/资料/{资料编号}/下载`，搜索接口为 `/接口/搜索?关键词=...`。管理员可为课程创建只读分享链接（`POST /接口/课程/{编号}/分享`），分享页为 `/分享/{令牌}`，公开查看接口为 `/接口/分享/{令牌}`。热门与最新资料为 `/接口/热门`、`/接口/最新`；`/接口/概览` 仅管理员；`/接口/我的会话` 查看并管理自己的登录设备；资料评论为 `/接口/资料/{编号}/评论`（发表用 POST，删除用 `DELETE /接口/评论/{编号}`）；自助注册为 `POST /接口/注册`。课程和资料列表、搜索结果返回 `items`、`total`、`page`、`page_size` 和 `total_pages`，可用 `page` 与 `page_size` 分页。接口调用始终返回 JSON；浏览器直接访问出错地址时会拿到中文错误页。

搜索接口还支持筛选与排序参数：`课程编号`、`类型`（扩展名，如 `pdf`）、`起始时间`、`结束时间`（`YYYY-MM-DD`）、`排序`。排序取值既可用英文 `newest` / `oldest` / `name` / `size`，也可用对应的中文 `最新` / `最早` / `标题` / `大小`；关键词与筛选条件之间是「与」的关系，只有筛选条件、没有关键词时同样会按条件列出资料。

首页在未登录时会显示一条访客提示，说明登录后可以上传资料、查看「我的上传」，管理员登录后还能管理用户。资料上传、审核状态查看与用户管理面板都是登录后才出现的，未登录访客只会看到课程浏览与搜索筛选。

所有 API 错误使用统一结构：`error.code` 为机器可读错误码，`error.message` 为中文提示，`error.request_id` 可用于查询日志。为兼容旧客户端，顶层 `detail` 字段仍保留。审计列表（`/接口/审计`）除 `page`/`page_size` 外还支持 `游标`：传入上一页最后一条的编号，取编号更小的记录，避免持续写入时按 offset 翻页跳条或重复。课程与资料编辑带乐观锁：响应里的 `version` 回传到编辑请求即可，版本不一致返回 `409`；不传则退化为「后写覆盖」。

数据库默认保存为 `data/coursebox.db`，也可以通过 `COURSEBOX_DB` 环境变量指定其他 SQLite 文件路径。上传目录可通过 `COURSEBOX_UPLOAD_DIR` 配置，单文件大小可通过 `COURSEBOX_MAX_FILE_SIZE` 配置，允许扩展名可通过逗号分隔的 `COURSEBOX_ALLOWED_EXTENSIONS` 配置。

## 运行测试

```powershell
py -m ruff check .
py -m pytest -q
```

测试按域拆成 18 个文件（公共夹具在 `tests/conftest.py`），共 166 个用例，覆盖健康检查（含缓存）、页面路由与错误响应、安全响应头、限流（IP 与账户写）、接口文档 CSP 与本地化、请求体上限（Content-Length 与分块）、课程增删改查与分页、课程标签、编辑乐观锁（含并发）、资料上传下载预览、可执行内容拦截、上传配额（单课程/站点/单用户，含并发）、重复检测、搜索与命中字段与可见性、登录会话与登录设备、自助注册（含每 IP 一个）、管理员保留（含并发）、反向代理下的来源识别、回收站（含批量）、打包下载、批量操作、审计日志（含游标分页）、只读分享链接、下载计数与热门/最新、站点概览、资料评论、CSV 导出、维护与备份轮转，另有一个用例专门校验前端 `fetch` 与后端路由的一致性。

仓库自带 GitHub Actions 工作流 `.github/workflows/ci.yml`，在 Python 3.11/3.12/3.13/3.14 上先跑 `ruff check .` 再跑 `pytest`；其中 3.14 那条腿额外统计覆盖率并要求不低于 90%（`--cov-fail-under=90`），并跑一次依赖安全扫描（`pip-audit`，先只报告不阻断）。另有一个 `smoke` 任务：起真实 `uvicorn` 后执行 `scripts/smoke.py`，覆盖 TestClient 会绕过的那部分（中间件顺序、路由匹配）。推送或提交 PR 时自动执行。

本地也可以对已启动的服务跑冒烟：

```powershell
py -m uvicorn app.main:app --port 8000
py scripts\smoke.py --base-url http://127.0.0.1:8000
```

## 部署与运维

生产环境建议使用反向代理提供 HTTPS，并将 `COURSEBOX_HOST` 设置为 `127.0.0.1`，仅由反向代理访问 Uvicorn。生产环境必须显式设置 `COURSEBOX_ADMIN_PASSWORD`（至少 8 位），否则应用拒绝启动。应用会在请求完成时输出一行 JSON 日志，包含事件、请求 ID、方法、路径、状态码和耗时；发生未处理异常时会记录堆栈，但 API 只向客户端返回通用错误信息。

健康检查地址为 `/接口/健康`（ASCII 别名 `/api/health`，`render.yaml` 用它做平台健康检查）。响应会分别检查数据库完整性、上传目录可写性和磁盘剩余空间；任一检查失败时返回 HTTP 503。为避免泄露服务器路径，失败原因只写日志，响应里给通用中文提示。监控应同时关注 HTTP 状态码和响应中的 `checks` 字段。

审计日志、登录失败记录、过期会话与回收站按保留期自动清理（启动时清理一次），默认审计日志保留 90 天（`COURSEBOX_AUDIT_RETENTION_DAYS`）。也可以手动执行：

```powershell
py -m app.maintenance
```

### 备份与轮转

备份使用 SQLite 在线备份接口，不需要停止服务；数据库通过 `PRAGMA quick_check` 校验后才会改名为正式备份，同时会把上传目录打包成同名时间戳的 zip：

```powershell
py -m app.backup --destination backups --keep 7
# 或使用脚本 / PowerShell 封装
py scripts\backup.py --destination backups --keep 7
.\scripts\backup.ps1 -Destination backups -Keep 7
```

`--keep` 表示保留最近 N 组备份（每组包含数据库和上传归档），更旧的会被自动删除；`--keep 0` 表示全部保留，`--no-uploads` 表示只备份数据库。默认输出目录为项目下的 `backups/`（可用 `COURSEBOX_BACKUP_DIR` 覆盖），默认保留份数取 `COURSEBOX_BACKUP_KEEP`（默认 7）。

> 注意：数据库与上传目录是**两个时刻**的快照（先备份库、再打包文件），两步之间发生的删除会造成归档缺文件。生产建议在低峰或暂停写入时备份（见「已知局限」）。

恢复前先停止应用，恢复脚本会校验备份完整性；覆盖已有数据库时显式使用 `-Force`，并自动保存一个 `.before-restore` 文件。备份里的上传归档用 `-Uploads` 一并还原：

```powershell
.\scripts\restore.ps1 -Backup .\backups\coursebox-20260908-120000.db -Force
.\scripts\restore.ps1 -Backup .\backups\coursebox-20260908-120000.db `
    -Uploads .\backups\uploads-20260908-120000.zip -Force
```

### 注册定时备份

Windows 计划任务每天凌晨 3 点执行一次，保留最近 7 组：

```powershell
$action = New-ScheduledTaskAction -Execute "py" `
    -Argument "scripts\backup.py --destination backups --keep 7" `
    -WorkingDirectory "C:\Users\璃绪\Desktop\study\CourseBox"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "CourseBox 每日备份" -Action $action -Trigger $trigger -RunLevel Highest
```

也可以用 `schtasks` 一行注册：

```powershell
schtasks /Create /TN "CourseBox 每日备份" /SC DAILY /ST 03:00 ^
    /TR "py C:\Users\璃绪\Desktop\study\CourseBox\scripts\backup.py --destination backups --keep 7"
```

Linux/macOS 用 cron 每天 3 点执行，保留最近 7 组：

```cron
0 3 * * * cd /srv/CourseBox && /usr/bin/python3 -m app.backup --destination backups --keep 7 >> /var/log/coursebox-backup.log 2>&1
```

备份目录建议放在另一块磁盘或同步到远端存储；只保留本机备份无法应对磁盘故障。

## 已知局限

这是一个面向单个班级 / 课程组的小站，下面这些取舍是**有意为之**，不是遗漏：

- **只支持单实例部署。** 数据库是 SQLite（单写者），限流计数存在进程内存里。同时跑多个进程或实例时，每个实例各算各的限额，实际放行量会变成「实例数 × 配置额度」，SQLite 的并发写也会成为瓶颈。要水平扩展得先换掉这两处（外部数据库 + 共享的限流存储）。
- **静态资源版本号按进程缓存。** `asset_version` 取资源内容哈希，进程内只算一次。因为结果只由文件内容决定，多实例算出来一致，这一项本身不影响多实例；只是换上新资源后要重启（或等进程重算）版本号才会更新。
- **数据库迁移是手写的 `ALTER`。** 加列靠 `PRAGMA table_info` 判断后再补，当前结构版本记在 `PRAGMA user_version`（见 `app/db.py` 的 `SCHEMA_VERSION`）。没有引入 Alembic 之类的迁移框架，规模明显增长前够用。
- **前端按功能拆成三段经典脚本（`app.js` / `app-2.js` / `app-3.js`），共享全局作用域。** 没有构建链、没有 ES 模块——这是刻意的（不引入 node/npm 与 CDN，保证离线可用）。三段按原顺序用 `<script>` 依次加载，执行语义与单文件一致；三段都计入内容哈希版本号。前后端接口的一致性由 `tests/test_frontend_contract.py` 兜底（会扫描全部三段）。
- **接口文档的中文化仍在 `app/main.py` 里做后处理。** 生成 OpenAPI 后再按显式映射改名：模型名、路径参数、属性标题各一张表，`$ref` 按组件全名精确替换（旧实现用子串替换，会把 `CourseCreate` 误伤成「课程Create」，已修）。新增模型若忘了登记会退回英文；已加测试守住 `Course` / `ShareLink` 等关键名。
- **请求体上限有两条防线。** 带 `Content-Length` 的请求在读取正文前直接 413；分块传输（`Transfer-Encoding: chunked`，没有该头）由 ASGI 层按实际读到的字节数兜底。生产环境仍建议再由反向代理限制请求体大小。
- **代理来源识别要显式开启。** 默认不信任 `X-Forwarded-For`（直连时它能被伪造、用来绕过限流）；反向代理部署需设 `COURSEBOX_TRUST_PROXY=true`，否则限流与登录锁定会退化成按代理 IP 计数。
- **接口文档默认开启。** `/接口文档`、`/接口说明`、`/接口定义` 对外可访问；关闭用 `COURSEBOX_ENABLE_DOCS=false`，此时需自行为 Swagger/ReDoc 页面设置允许 CDN 的 CSP（当前实现会给这两个前缀下发专用策略）。
- **分享链接锁不住资料字节。** 本站课程浏览与「已通过」资料下载本来就是公开的，分享链接的有效期与撤销只作用于「分享页」本身；拿到链接的人即使链接过期，只要知道资料编号仍能直接下载。要真正限制访问，需把课程/资料改成默认私有（等于改产品定位）。
- **下载计数会给每次下载一次写。** 为了热门榜，匿名下载也会对 `files.download_count` 做一次单行 `UPDATE`；相比「匿名下载不写审计」是原地更新、不会让表膨胀，但仍是每个下载一次写锁。量级再大应改为内存累计 + 定时落库。
- **备份不是同一时刻的快照。** `py -m app.backup` 先在线备份数据库、再打包上传目录；两步之间发生的删除会造成「备份库里有记录、归档里没有对应文件」（数据库 `quick_check` 仍会通过）。生产环境应在低峰或暂停写入时备份。
- **评论用轮询刷新，不是真实时。** 评论弹层打开时每 4 秒拉一次；要「有新评论立刻出现」需上 SSE/WebSocket（本项目是单实例，进程内广播即可，但要注意反向代理缓冲与 Render 免费层休眠）。
- **「一个 IP 一个账户」是软限制。** 校园网等共用出口 IP 下，整片网络只能注册一个账户；而换 IP（手机流量/代理）即可绕过。它只防手滑、不防刷，真正的兜底是接口限流与管理员删除/停用。

## 截图

当前版本未在仓库中提交截图文件。启动服务后可截取首页课程列表、课程详情页和搜索结果页作为项目展示图。
