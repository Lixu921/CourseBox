# 课盒子

课盒子是一个基于 FastAPI 和 SQLite 的课程资料共享小站。用户可以按课程浏览资料、上传文件、下载资料，也可以按课程名、资料标题或原文件名搜索。

## 功能

- 首页展示课程列表
- 课程详情页展示资料并支持上传
- 上传文件大小限制为 20 MB
- 使用随机文件名保存上传内容，保留原始文件名用于展示和下载
- 直接下载课程资料
- 搜索课程名、资料标题和原文件名
- 前端提供加载、空结果和请求失败提示

## 目录

```text
CourseBox/
├─ app/
│  ├─ api/courses.py    # 课程接口
│  ├─ api/files.py      # 资料上传、下载和搜索接口
│  ├─ db.py             # SQLite 连接和建表
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
│  ├─ backup.ps1        # SQLite 在线备份
│  └─ restore.ps1       # 备份校验和恢复
├─ .env.example         # 环境配置示例
├─ pyproject.toml       # 项目元数据、pytest 和 Ruff 配置
├─ data/                # 本地 SQLite 数据库，不提交到 Git
└─ uploads/             # 上传文件，不提交到 Git
```

## 环境要求

- Python 3.14
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
py -m uvicorn app.main:app --port 8000
```

Windows 也可以使用启动脚本：

```powershell
.\scripts\start.ps1 -Port 8000
```

如果 Windows 的 `py` 或 `python` 命令被系统执行别名拦截，可先指定解释器：`$env:COURSEBOX_PYTHON = "C:\Python314\python.exe"`。

启动服务后，可以打开[应用首页](http://127.0.0.1:8000/)和[接口文档](http://127.0.0.1:8000/%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3)。如果需要让其他设备访问，请先阅读[部署说明](DEPLOY.md)。

网页和接口统一使用中文路径：课程页为 `/课程`，样式和脚本为 `/资源/样式.css`、`/资源/脚本.js`，课程接口为 `/接口/课程`，资料接口为 `/接口/课程/{编号}/资料`，下载地址为 `/接口/资料/{资料编号}/下载`，搜索接口为 `/接口/搜索?关键词=...`。课程和资料列表、搜索结果返回 `items`、`total`、`page`、`page_size` 和 `total_pages`，可用 `page` 与 `page_size` 分页。

所有 API 错误使用统一结构：`error.code` 为机器可读错误码，`error.message` 为中文提示，`error.request_id` 可用于查询日志。为兼容旧客户端，顶层 `detail` 字段仍保留。

数据库默认保存为 `data/coursebox.db`，也可以通过 `COURSEBOX_DB` 环境变量指定其他 SQLite 文件路径。上传目录可通过 `COURSEBOX_UPLOAD_DIR` 配置，单文件大小可通过 `COURSEBOX_MAX_FILE_SIZE` 配置，允许扩展名可通过逗号分隔的 `COURSEBOX_ALLOWED_EXTENSIONS` 配置。

## 运行测试

```powershell
py -m pytest -q
```

测试覆盖健康检查、页面路由、课程创建、详情、分页、编辑和删除、资料上传、重复检测、元数据、清理、文件下载以及搜索接口，也覆盖统一错误响应和请求日志。

## 部署与运维

生产环境建议使用反向代理提供 HTTPS，并将 `COURSEBOX_HOST` 设置为 `127.0.0.1`，仅由反向代理访问 Uvicorn。应用会在请求完成时输出一行 JSON 日志，包含事件、请求 ID、方法、路径、状态码和耗时；发生未处理异常时会记录堆栈，但 API 只向客户端返回通用错误信息。

健康检查地址为 `/接口/健康`。响应会分别检查数据库完整性、上传目录可写性和磁盘剩余空间；任一检查失败时返回 HTTP 503。监控应同时关注 HTTP 状态码和响应中的 `checks` 字段。

SQLite 备份使用在线备份接口，不需要停止服务：

```powershell
.\scripts\backup.ps1 -Destination backups
```

恢复前先停止应用，恢复脚本会校验备份完整性；覆盖已有数据库时显式使用 `-Force`，并自动保存一个 `.before-restore` 文件：

```powershell
.\scripts\restore.ps1 -Backup .\backups\coursebox-20260908-120000.db -Force
```

数据库和上传目录需要分别纳入备份策略。数据库备份不包含上传文件，上传目录应使用文件系统快照或单独的归档任务备份。

## 截图

当前版本未在仓库中提交截图文件。启动服务后可截取首页课程列表、课程详情页和搜索结果页作为项目展示图。
