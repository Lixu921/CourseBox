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

## 启动项目

```powershell
py -m uvicorn app.main:app --port 8000
```

浏览器打开 <http://127.0.0.1:8000/>，接口文档位于 <http://127.0.0.1:8000/接口文档>。

网页和接口统一使用中文路径：课程页为 `/课程`，样式和脚本为 `/资源/样式.css`、`/资源/脚本.js`，课程接口为 `/接口/课程`，资料接口为 `/接口/课程/{编号}/资料`，下载地址为 `/接口/资料/{资料编号}/下载`，搜索接口为 `/接口/搜索?关键词=...`。课程和资料列表、搜索结果返回 `items`、`total`、`page`、`page_size` 和 `total_pages`，可用 `page` 与 `page_size` 分页。

数据库默认保存为 `data/coursebox.db`，也可以通过 `COURSEBOX_DB` 环境变量指定其他 SQLite 文件路径。上传目录可通过 `COURSEBOX_UPLOAD_DIR` 配置，单文件大小可通过 `COURSEBOX_MAX_FILE_SIZE` 配置，允许扩展名可通过逗号分隔的 `COURSEBOX_ALLOWED_EXTENSIONS` 配置。

## 运行测试

```powershell
py -m pytest -q
```

测试覆盖健康检查、页面路由、课程创建、详情、分页、编辑和删除、资料上传、重复检测、元数据、清理、文件下载以及搜索接口。

## 截图

当前版本未在仓库中提交截图文件。启动服务后可截取首页课程列表、课程详情页和搜索结果页作为项目展示图。
