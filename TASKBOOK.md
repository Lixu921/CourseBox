# CourseBox 任务书(TASKBOOK)

> 执行者:Codex / 任何 AI 工程师
> 目标:做出一个**带完整网页**的课程资料共享小站,分 8 个里程碑推进。
> 规则:每个里程碑都有**客观验收命令**,跑不过就自己修,修不好就停下汇报。

## 0.5 项目起点(重要)
**当前目录是空的,除本任务书外没有任何文件。你必须从零初始化**:
在 M0 里自己完成 `git init`、创建 `.gitignore`、`requirements.txt`、装依赖、建目录、写最小 FastAPI 骨架。
不要假设任何文件已存在,一切自己建。

## 0. 总体目标与范围

做一个校园"课程资料共享小站":老师/同学能按课程上传资料(课件、往年题),其他人能浏览、搜索、下载。

用户故事(网页必须支持):
1. 打开首页 → 看到课程列表 + 搜索框
2. 点击某门课 → 课程详情页:该课文件列表 + "上传资料"表单
3. 上传成功 → 文件出现在列表,可点击下载
4. 首页搜索关键词 → 显示命中的资料,可跳转下载

**MVP 边界:不做**登录注册、点赞评论、通知爬虫、分页、多学院、消息推送。

## 1. 技术栈与环境(严格遵守)

- 后端:**FastAPI**(Python)。数据库:**SQLite**(用内置 `sqlite3`,不要装别的数据库)。
- 前端:**纯 HTML + CSS + 原生 JavaScript**。**禁止**使用 node/npm、禁止引外部 CDN(离线也要能跑),样式自己写,界面中文、简洁、能看。
- 运行与安装:所有命令用 **`py`** 开头(Windows 上 `python` 可能是商店占位程序,不可靠)。
- 依赖安装(网络受限,必须用清华镜像并绕过本地代理):
  `py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt`
  (requirements.txt 应含:fastapi, uvicorn, pytest, httpx)
- Python 版本 3.14,`sqlite3` 为标准库。
- **只允许在 `C:\Users\璃绪\Desktop\CourseBox` 目录内创建/修改文件。**
- **禁止修改系统代理设置、禁止改动本目录之外的一切。**

## 2. 目录规范(必须按这个长)

```
CourseBox/
├─ app/
│  ├─ main.py          # FastAPI 入口:创建 app、挂路由、挂静态页
│  ├─ db.py            # 连库+建表(读取环境变量 COURSEBOX_DB 指定库文件路径,默认 data/coursebox.db)
│  ├─ schemas.py       # Pydantic 请求/响应模型
│  └─ api/
│     ├─ __init__.py
│     ├─ courses.py    # 课程:列出/新增
│     └─ files.py      # 资料:某课列表/上传/下载/搜索
├─ static/
│  ├─ index.html       # 首页:课程列表+搜索框
│  ├─ course.html      # 课程详情页:文件列表+上传表单
│  ├─ style.css
│  └─ app.js           # fetch 调用后端
├─ tests/
│  └─ test_api.py      # TestClient 集成测试(每个里程碑都要跑)
├─ data/               # SQLite 库文件放这,须被 .gitignore 排除
├─ uploads/            # 上传文件放这,须被 .gitignore 排除
├─ requirements.txt    # 由 M0 创建
└─ .gitignore          # 由 M0 创建,须排除 data/ uploads/ config.json __pycache__
```

## 3. 数据模型

`courses` 表:id(自增), name(课程名,必填), college(学院,可空), semester(学期,可空)。
`files` 表:id(自增), course_id(外键→courses.id), title(展示标题), filename(落盘后的文件名), original_name(原始文件名), size(字节), upload_time(默认当前时间)。

落盘规则:上传文件统一存到 `uploads/` 下,落盘文件名用 `uuid` 或 `时间戳+安全后缀`,**绝不使用用户原始文件名作为落盘名**(防路径穿越)。
数据库库文件路径可用环境变量 `COURSEBOX_DB` 覆盖(测试用临时库,别污染真库)。

## 4. 里程碑与验收(按顺序执行,过一关 commit 一次)

> 通用规矩:每完成一个里程碑,先跑该里程碑验收命令;**红了就自己读报错修复,同一问题最多试 3 次,3 次修不好立刻停下,把报错贴给用户。** 通过后 `git add -A && git commit -m "完成 Mx: <一句话>"`。

### M0 — 从零初始化 + 骨架跑通
- 在项目根目录执行 `git init -b main`。
- 创建 `.gitignore`:至少排除 `__pycache__/`、`*.pyc`、`.venv/`、`data/`、`uploads/`、`config.json`、`.env`。
- 创建 `requirements.txt`(含 fastapi、uvicorn、pytest、httpx)并安装依赖:
  `py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt`
  (若因本地代理连不上,先在同一命令前设 `NO_PROXY=*` 再试;安装期间不要改系统代理设置)
- 创建目录结构:`app/`、`app/api/`、`static/`、`tests/`、`data/`、`uploads/`(目录规范见第 2 节)。
- `app/main.py` 写最小 FastAPI:title 为 "CourseBox 课盒子",`GET /` 返回 `{"app": "CourseBox", "status": "ok", "docs": "/docs"}`。
- `tests/test_api.py` 写最小测试:TestClient 请求 `GET /` 断言 status 200 且 json 含 app=CourseBox。
- 验收:
  1. `py -m pytest -q` 通过。
  2. `py -c "from app.main import app; print(app.title)"` 能打印标题不报错。
- commit:`完成 M0: 从零初始化骨架`。

### M1 — 数据层 + 课程接口
- 建 `app/db.py`(建表、get_db)、`app/schemas.py`、`app/api/courses.py`,挂载路由。
- `GET /api/courses` → 返回课程列表 JSON。
- `POST /api/courses` → body `{"name": "...", "college": "...", "semester": "..."}`,name 必填,新增成功返回该课程。
- 验收:在 `tests/test_api.py` 里用 TestClient 写用例:新增一门课 → 列表接口能看到它;name 为空时返回 422。`py -m pytest -q` 全绿。

### M2 — 上传与文件列表
- `POST /api/courses/{course_id}/files`:multipart 表单,字段 `title` + 文件 `file`。文件存到 `uploads/`,库表 `files` 入库;文件大小上限 20MB,超限返回 413。course 不存在返回 404。
- `GET /api/courses/{course_id}/files` → 该课文件列表。
- 验收:TestClient 写用例:造临时文件上传 → 列表能看到;上传到不存在课程返回 404。`pytest` 全绿。

### M3 — 下载与搜索
- `GET /api/files/{file_id}/download` → 用 `FileResponse` 返回原文件(Content-Disposition 用原始文件名)。
- `GET /api/search?q=关键词` → 在 files.title 与 original_name 里做不区分大小写模糊匹配(也顺带匹配课程名),返回结果含课程信息便于前端跳转。
- 验收:下载用例断言返回内容一致;搜索用例造"数据结构期中.pdf"搜"数据结构"能命中。`pytest` 全绿。

### M4 — 首页网页
- 建 `static/index.html` + `style.css` + `app.js`;FastAPI 把 `static/` 挂成静态目录,并让 `GET /` 返回 index.html(可直接用 StaticFiles + html=True,或显式路由)。
- 首页要:标题"课盒子 · 课程资料共享";**用 fetch 调 `GET /api/courses` 渲染课程卡片列表**;每张卡片链接到 `course.html?id=<id>&name=<课程名>`;顶上一个搜索框。
- 验收:启动 `py -m uvicorn app.main:app --port 8000`,浏览器打开 `http://127.0.0.1:8000/` 能看到页面;手动 POST 加过课程后首页能列出。(若机器无浏览器,改用 curl 断言 `GET /` 返回 200 且含 html 与课程接口路径即可)

### M5 — 课程详情页 + 上传
- `static/course.html`:读 URL 的 id/name 显示课程名;调 `GET /api/courses/{id}/files` 渲染文件列表(每条含下载链接 `download.html?id=`… 或直接指向 `/api/files/{id}/download`);**上传表单**:文件选择 + 标题输入 + 按钮,用 fetch `FormData` POST 到上传接口,成功刷新列表。
- 验收:浏览器里能在该页上传一个 txt,列表立刻出现并可点下载;或 curl/TestClient 验证页面与上传链路。

### M6 — 搜索页联动 + 样式打磨
- 首页搜索框回车 → 调 `GET /api/search?q=...` → 结果列表渲染(显示资料名、所属课程,可跳下载/课程页);空结果显示"没有找到相关资料"。
- 统一页面顶部导航(首页/回到顶部)、错误提示(接口失败给出友好中文提示,不白屏)。
- 验收:浏览器搜索"数据结构"能出结果;断网/无结果时有提示,页面不崩。

### M7 — 收尾整理
- 写 `README.md`:项目简介、功能列表、目录说明、本地运行步骤(安装命令、启动命令、测试命令)、截图占位。
- 确认 `.gitignore` 已排除 `data/ uploads/ __pycache__/`;确认没有把任何文件传进 `data/`、`uploads/`。
- 全部 `pytest` 通过后,做一次最终 commit,并给我一份总结。

## 5. 执行规矩(必须遵守)

1. **小步走**:严格按 M0→M7 顺序,一次只做当前里程碑。
2. **先测试后通过**:每一关都先跑 `py -m pytest -q`。
3. **commit 时机**:每过一个里程碑就 commit,信息格式 `完成 Mx: <描述>`。
4. **自愈上限**:同一错误自己尝试修复最多 3 次;第 3 次仍失败 → 立即停止,把报错和已做的尝试汇报给用户,不要继续硬闯。
5. **代码风格**:函数短小、职责单一;界面文字用中文;不要写多余注释,但关键逻辑可加一行中文说明。
6. **不越界**:MVP 范围之外(登录/点赞/通知/分页)一律不做;不要动 `.gitignore` 排除项之外的数据目录;不要把上传目录或数据库提交进 git。
7. **遇到安装失败**:先看是否代理问题,若连不上 pypi 就用清华镜像 + 在命令前临时设 `NO_PROXY=*`。

## 6. 完成后的汇报模板(贴给我)

- 每个里程碑一句"做了什么 + 验收结果"
- 卡住过的地方与最终解法
- 当前 git log(最近 8 条)
- 浏览器截图或页面可访问地址
- 下一步建议(可选)
