# CourseBox 第十七轮任务书：前端经典脚本拆分

## 背景

`static/app.js` 已涨到约 2100 行，阅读与改动成本偏高。评估过拆成原生 ES 模块，但项目
**没有 JS 运行测试**（当初为「不引入 Node/构建链」放弃了 jsdom），而 `app.js` 顶部有 99 个
DOM 常量与约 30 个共享可变全局，改成 ESM 属于结构性重写，一旦出错 pytest 与 `smoke.py`
都抓不到。

因此本轮选择**低风险的经典脚本拆分**：把单文件按原顺序切成三段，HTML 用多个 `<script>`
依次加载。经典脚本共享全局词法作用域、按加载顺序执行，因此「三段顺序加载」的语义与单文件
**完全一致**，不改变任何行为。

## 设计

- 用内容锚点（不是行号）切分，避免 CRLF/LF 计数差异：
  - `app.js`：开头到 `loadCourseFiles` 之前（DOM 常量、格式化/高亮、鉴权、搜索、课程与资料渲染）。
  - `app-2.js`：`loadCourseFiles` 到 `loadUsers` 之前（资料加载、预览、上传、导出、课程管理、分享按钮）。
  - `app-3.js`：`loadUsers` 到结尾（用户/审计/回收站/我的上传、`readError`、`init*` 与 `bootstrap()`）。
- 三段都计入 `VERSIONED_ASSETS`，入口版本号随任一段变化。
- 新增 `/资源/脚本2.js`、`/资源/脚本3.js` 路由（`/资源/脚本.js` 保留为第一段）。
- `index.html`、`course.html` 依次引入三段，均带 `?v={{asset_version}}`。
- 契约测试改为读取三段合并后的源码。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 首页/课程页引用三段带版本号的脚本；三个 URL 都 200。
- 前端 `fetch` 契约、页面 id 契约仍通过（扫描三段）。
- `app.js + app-2.js + app-3.js` 的内容等于拆分前的 `app.js`（按原顺序拼接）。
- 真实服务冒烟通过。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `static/app.js`、`static/app-2.js`、`static/app-3.js` | 按锚点切分，内容为原文件的连续三段 |
| `app/main.py` | `VERSIONED_ASSETS` 加后两段；新增两条中文脚本路由 |
| `static/index.html`、`static/course.html` | 依次引入三段 |
| `tests/test_frontend_contract.py` | 改用三段合并源码 |
| `tests/test_platform.py` | 断言三段脚本可访问、页面引用三段 |
| `README.md` | 「已知局限」相应更新 |

验证：`ruff` 全绿，`pytest` 150 passed（本轮不改变用例数）；真实 uvicorn 下三段脚本
200、`scripts/smoke.py` 通过。
