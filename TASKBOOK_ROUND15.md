# CourseBox 第十五轮任务书：只读分享链接

## 背景与定位

管理员可为某门课生成一条带有效期的链接，分享页只展示该课程「已通过」的资料并给出下载入口。

**先明确局限**：本站课程浏览与已通过资料下载本来就是公开的，所以分享链接是**便捷链接**，
不是访问控制——有效期与撤销只作用于「分享页」，锁不住资料字节。要真正限制访问需改成默认
私有，属于改产品定位。这一点写进了 README「已知局限」。

## 设计

- 新表 `share_links(id, token, course_id, created_by, note, created_at, expires_at)`，
  结构版本升到 v7（`CREATE TABLE IF NOT EXISTS`，老库启动即建）。
- 管理员接口：
  - `POST /接口/课程/{编号}/分享`：body `{days?: 1..90, note?}`，生成 `secrets.token_urlsafe(24)`。
  - `GET /接口/课程/{编号}/分享`：列出该课程的链接。
  - `DELETE /接口/分享/{编号}`：撤销。
  - 审计复用 `create`/`delete` + 实体 `course`，避免扩展审计枚举。
- 公开接口：`GET /接口/分享/{token}` → 课程信息 + 已通过资料列表；不存在 404、过期 410。
- 分享页 `/分享/{token}`（`static/share.html` + `static/share.js`，纯 `textContent` 渲染）：
  从地址取 token，调公开接口渲染资料列表与下载链接。
- 课程页管理员操作区新增「分享链接」按钮：prompt 天数 → 创建 → 弹窗给出完整 URL。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 创建返回 token 与 `/分享/{token}`；匿名可打开分享页与公开接口。
- 分享内容只含已通过资料（待审不在内）。
- 非管理员创建 403；撤销后 404；过期后 410。
- 前端 `fetch` 与后端路由一致性测试通过（`/api/courses/{id}/share`）。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/db.py` | `share_links` 表；`SCHEMA_VERSION = 7` |
| `app/schemas.py` | `ShareCreate`/`ShareLink`/`ShareView`、`MAX_SHARE_DAYS` |
| `app/api/share.py` | 增删查 + 公开查看 |
| `app/main.py` | 注册路由、`/分享/{token}` 页面、`410 -> gone` 错误码 |
| `static/share.html`、`static/share.js`、`static/app.js` | 分享页与「分享链接」按钮 |
| `tests/test_share.py` | 生命周期与过期两条用例 |
| `README.md` | 功能、路由说明、已知局限、用例数 |

验证：`ruff` 全绿，`pytest` 149 passed（第十四轮 147 → 149）。
