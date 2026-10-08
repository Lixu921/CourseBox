# CourseBox 第二十轮任务书：资料评论（第一档）

## 背景

给资料加评论区。按之前讨论，**先做第一档：评论 + 轮询**（简单档），不引入 SSE/长连接；
要做真实时再单独升级。

## 设计

- 新表 `comments(id, file_id, user_id, body, created_at)`，外键分别 `ON DELETE CASCADE`
  （资料或用户被删，评论一并清理），`idx_comments_file_id` 索引；结构版本升到 v9。
- 接口：
  - `GET /接口/资料/{编号}/评论`：分页查看（编号倒序，最新在前），匿名可读。
  - `POST /接口/资料/{编号}/评论`：登录可发，body 纯文本 1..2000 字（去首尾空白）。
  - `DELETE /接口/评论/{编号}`：作者或管理员可删。
- **可见性跟资料一致**：待审/已拒绝资料的评论对非本人返回 404（复用资料的可见规则）。
- 审计新增动作 `comment`（发表），删除评论记 `delete`/实体 `file`；审计筛选下拉补「评论」。
- `files` 列表返回 `comment_count`（相关子查询），供前端在按钮上显示条数。
- 前端：资料行加「评论 N」按钮 → 打开评论弹层（复用预览弹层的样式），展示列表 + 输入框；
  打开期间每 4 秒轮询刷新，关闭停止；发表/删除后刷新列表并更新资料行计数。
- 评论一律用 `textContent` 渲染，绝不拼 HTML（防 XSS）。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 匿名能读、不能发（401）；发表后首尾空白被去掉、带作者用户名；`comment_count` 出现在资料列表。
- 空/超长/缺字段返回 422。
- 作者可删自己的、管理员可删别人的、别人删我的 403、删不存在 404。
- 待审资料的评论对匿名与陌生人 404，对本人与管理员可见。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/db.py` | `comments` 表 + 索引；`SCHEMA_VERSION = 9` |
| `app/schemas.py` | `CommentCreate`/`Comment`/`CommentPage`、`MAX_COMMENT_LENGTH` |
| `app/api/comments.py` | 查看 / 发表 / 删除 + 可见性校验 |
| `app/api/files.py` | `comment_count` 进各查询与 `file_response` |
| `app/api/audit.py`、`static/index.html` | 审计动作 `comment` 与筛选项 |
| `static/course.html`、`app.js`、`app-2.js`、`app-3.js`、`style.css` | 评论弹层与轮询 |
| `tests/test_comments.py` | 新增四条用例 |
| `README.md` | 功能、路由、已知局限、用例数 |

验证：`ruff` 全绿，`pytest` 161 passed（第十九轮 157 → 161）。
