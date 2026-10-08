# CourseBox 第十四轮任务书：课程标签

## 背景

课程只有名称、学院、学期，课程一多就不好归类与查找。本轮给课程加分类标签。

## 设计

- `courses` 加一列 `tags TEXT`（逗号分隔），结构版本升到 v6；老库由 `migrate_courses_table` 补列。
- 请求模型 `CourseCreate`/`CourseUpdate` 接受 `tags: list[str] | None`，规整规则：去空白、去重、
  单标签 ≤30 字、最多 10 个（`normalize_tags`）；也兼容逗号分隔的字符串（前端表单直接提交文本）。
- 响应模型 `Course` 的 `tags` 始终是 `list[str]`（`parse_tags` 把库里字符串读回列表）。
- `/接口/课程` 新增 `标签` 精确筛选（两边补逗号匹配 `,tag,`，避免「大二」误撞「大二班」），
  并让标签参与 `关键词` 搜索。
- 前端：创建课程表单加「标签」输入；课程卡片展示标签小圆角块，关键词命中标签时补「命中：标签」。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 提交 `["必修","  大二  ","必修"]` → 存成 `["必修","大二"]`。
- `标签=必修` 精确命中；`标签=必` 不命中（不做子串）。
- `关键词=大二` 能搜到该课程；编辑与清空标签都生效。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/db.py` | `courses.tags`；`migrate_courses_table` 补列；`SCHEMA_VERSION = 6` |
| `app/schemas.py` | `normalize_tags`/`serialize_tags`/`parse_tags`；`Course`/`CourseCreate`/`CourseUpdate` 的 tags |
| `app/api/courses.py` | 增删改查带 tags；`标签` 筛选；关键词纳入 tags |
| `static/index.html`、`static/app.js`、`static/style.css` | 标签输入、卡片展示与命中标签 |
| `tests/test_courses.py` | 新增 `test_course_tags`；更新既有期望值 |
| `README.md` | 功能与测试说明同步 |

验证：`ruff` 全绿，`pytest` 147 passed（第十三轮 146 → 147）。
