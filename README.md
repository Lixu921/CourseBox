# 课盒子

课盒子是一个基于 FastAPI 和 SQLite 的课程资料共享小站。用户可以按课程浏览资料、上传文件、下载资料，也可以按课程名、资料标题或原文件名搜索。

## 功能

- 首页展示课程列表，支持按课程、文件类型、上传时间范围筛选，并按最新、最早、标题或大小排序
- 搜索结果中的关键词在标题、文件名和课程名上高亮显示
- 课程详情页展示资料并支持上传，上传区支持拖拽与多选，逐个显示进度和结果
- PDF、图片和纯文本资料可以在弹层中在线预览，其余类型仍走下载
- 上传文件大小限制为 20 MB（另有单课程、站点总量与磁盘剩余空间三重配额保护）
- 使用随机文件名保存上传内容，保留原始文件名用于展示和下载
- 直接下载课程资料
- 搜索课程名、资料标题和原文件名；中文子串通过 FTS5 trigram 索引命中
- 三种角色：管理员可管理课程与用户，上传者提交的资料需审核，浏览者只读
- 「我的上传」列出自己提交的资料及其审核状态，待审核的可撤回
- 前端提供加载、空结果和请求失败提示

## 权限与账户

首次启动会创建 `COURSEBOX_ADMIN_USERNAME` 指定的管理员账户。登录后可在首页的「用户管理」面板查看用户列表、创建账户、调整角色、停用/启用账户和重置密码；系统始终保留至少一个启用的管理员，且不允许修改或停用当前登录账户。

非管理员上传的资料默认为待审核状态，管理员在课程页或资料列表上执行通过/拒绝。停用账户会立即失效其已登录会话，重置密码同样会作废该用户的全部会话。

## 目录

```text
CourseBox/
├─ app/
│  ├─ api/auth.py       # 登录、当前用户、退出
│  ├─ api/courses.py    # 课程接口
│  ├─ api/files.py      # 资料上传、下载、预览和搜索接口
│  ├─ api/users.py      # 管理员用户管理
│  ├─ backup.py         # 数据库与上传目录备份、轮转
│  ├─ db.py             # SQLite 连接和建表
│  ├─ maintenance.py    # 审计日志与登录记录的保留策略清理
│  ├─ main.py           # FastAPI 应用和页面路由
│  └─ schemas.py        # 请求、响应模型
├─ static/
│  ├─ index.html        # 首页
│  ├─ course.html       # 课程详情页
│  ├─ app.js            # 原生 JavaScript 交互
│  └─ style.css         # 页面样式
├─ tests/test_api.py    # API 和页面集成测试
├─ scripts/
│  ├─ start.ps1         # Windows 启动脚本
│  ├─ backup.ps1        # 备份脚本（调用 scripts/backup.py）
│  ├─ backup.py         # 计划任务入口，等价于 py -m app.backup
│  ├─ db_check.py       # 备份完整性校验
│  └─ restore.ps1       # 备份校验和恢复
├─ .github/workflows/   # GitHub Actions：ruff 检查 + pytest
├─ .env.example         # 环境配置示例
├─ pyproject.toml       # 项目元数据、pytest 和 Ruff 配置
├─ data/                # 本地 SQLite 数据库，不提交到 Git
├─ uploads/             # 上传文件，不提交到 Git
└─ backups/             # 备份输出目录，不提交到 Git
```

## 环境要求

- Python 3.11 及以上（本地在 3.14 上验证，CI 覆盖 3.11 / 3.12 / 3.13）
- Windows 环境建议使用 `py` 命令

## 安装依赖

```powershell
py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

如果本机代理导致安装失败，可以在该命令前临时设置 `NO_PROXY=*`，不要修改系统代理配置。

## 配置项目

复制 `.env.example` 为 `.env`，再按部署环境调整值。应用启动时会读取项目根目录 `.env`，但不会覆盖已有系统环境变量；生产环境可直接由进程管理器设置变量：

```powershell
$env:COURSEBOX_DB = "data/coursebox.db"
$env:COURSEBOX_UPLOAD_DIR = "uploads"
$env:COURSEBOX_ADMIN_PASSWORD = "请替换为至少 8 位密码"
```

支持的主要配置包括数据库路径、上传目录、单文件大小、允许扩展名、最低可用磁盘空间、日志级别、监听地址和端口。完整列表见 `.env.example`。

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

> 免费实例闲置约 15 分钟后会自动休眠，长时间没人访问时首次打开需要等待约 30-60 秒，属正常现象。

本地启动服务后，在运行服务的电脑上可以访问 `http://127.0.0.1:8000/`；同一局域网的同学请访问运行服务电脑的局域网 IPv4 地址，例如 `http://192.168.1.23:8000/`。启动脚本会打印可分享的局域网地址。若同学仍然无法访问，请确认双方连接的是同一个 Wi-Fi/局域网，并在 Windows 防火墙中允许 Python/Uvicorn 接受专用网络的入站连接；校园网可能会阻止设备之间互相访问。

如果需要重新部署或另建一份实例，可以[在 Render 上创建服务](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FLixu921%2FCourseBox)，或先阅读[部署说明](DEPLOY.md)。注意：这个链接是**部署入口**，打开后会进入 Render 控制台（用来创建/更新服务），并不是课盒子本身；部署完成后请使用 Render 分配的 `onrender.com` 地址访问应用。

网页和接口统一使用中文路径：课程页为 `/课程`，样式和脚本为 `/资源/样式.css`、`/资源/脚本.js`，课程接口为 `/接口/课程`，资料接口为 `/接口/课程/{编号}/资料`，下载地址为 `/接口/资料/{资料编号}/下载`，搜索接口为 `/接口/搜索?关键词=...`。课程和资料列表、搜索结果返回 `items`、`total`、`page`、`page_size` 和 `total_pages`，可用 `page` 与 `page_size` 分页。

搜索接口还支持筛选与排序参数：`课程编号`、`类型`（扩展名，如 `pdf`）、`起始时间`、`结束时间`（`YYYY-MM-DD`）、`排序`。排序取值既可用英文 `newest` / `oldest` / `name` / `size`，也可用对应的中文 `最新` / `最早` / `标题` / `大小`；关键词与筛选条件之间是「与」的关系，只有筛选条件、没有关键词时同样会按条件列出资料。

首页在未登录时会显示一条访客提示，说明登录后可以上传资料、查看「我的上传」，管理员登录后还能管理用户。资料上传、审核状态查看与用户管理面板都是登录后才出现的，未登录访客只会看到课程浏览与搜索筛选。

所有 API 错误使用统一结构：`error.code` 为机器可读错误码，`error.message` 为中文提示，`error.request_id` 可用于查询日志。为兼容旧客户端，顶层 `detail` 字段仍保留。

数据库默认保存为 `data/coursebox.db`，也可以通过 `COURSEBOX_DB` 环境变量指定其他 SQLite 文件路径。上传目录可通过 `COURSEBOX_UPLOAD_DIR` 配置，单文件大小可通过 `COURSEBOX_MAX_FILE_SIZE` 配置，允许扩展名可通过逗号分隔的 `COURSEBOX_ALLOWED_EXTENSIONS` 配置。

## 运行测试

```powershell
py -m ruff check .
py -m pytest -q
```

测试覆盖健康检查、页面路由、课程创建、详情、分页、编辑和删除、资料上传、重复检测、元数据、清理、文件下载、搜索与筛选、预览、用户管理、上传配额和备份轮转，也覆盖统一错误响应和请求日志。

仓库自带 GitHub Actions 工作流 `.github/workflows/ci.yml`，在 Python 3.11/3.12/3.13 上先跑 `ruff check .` 再跑 `pytest -q`；推送或提交 PR 时自动执行。

## 部署与运维

生产环境建议使用反向代理提供 HTTPS，并将 `COURSEBOX_HOST` 设置为 `127.0.0.1`，仅由反向代理访问 Uvicorn。生产环境必须显式设置 `COURSEBOX_ADMIN_PASSWORD`（至少 8 位），否则应用拒绝启动。应用会在请求完成时输出一行 JSON 日志，包含事件、请求 ID、方法、路径、状态码和耗时；发生未处理异常时会记录堆栈，但 API 只向客户端返回通用错误信息。

健康检查地址为 `/接口/健康`。响应会分别检查数据库完整性、上传目录可写性和磁盘剩余空间；任一检查失败时返回 HTTP 503。监控应同时关注 HTTP 状态码和响应中的 `checks` 字段。

审计日志和登录失败记录按保留期自动清理，默认审计日志保留 90 天（`COURSEBOX_AUDIT_RETENTION_DAYS`）。除启动时清理外，也可以手动执行：

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

恢复前先停止应用，恢复脚本会校验备份完整性；覆盖已有数据库时显式使用 `-Force`，并自动保存一个 `.before-restore` 文件：

```powershell
.\scripts\restore.ps1 -Backup .\backups\coursebox-20260908-120000.db -Force
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

## 截图

当前版本未在仓库中提交截图文件。启动服务后可截取首页课程列表、课程详情页和搜索结果页作为项目展示图。
