# CourseBox 第十三轮任务书：按上传者配额

## 背景

配额原本只有四层（单文件、单课程、站点总量、磁盘剩余），没有限制「某个上传者一共能传
多少」。一个人持续上传仍可能把全站空间占满。本轮补上第五层。

## 设计

- 新增 `COURSEBOX_MAX_USER_BYTES`（默认 0，表示不限制）。
- `upload_quota` 增加 `user_id` 参数，统计该上传者未删除资料的总量，加入「取最紧一条」的候选。
- `CourseQuota` 增加 `user_limit / user_used / user_remaining`；上传端点与配额接口都带上当前用户编号。
- 前端配额提示补「我的上传剩余 …」。
- 与既有配额一致：只统计未删除资料；`user_id` 为空（理论上不会）时不检查这一层。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 上传者用掉 800 / 1000 字节后，配额接口显示 `user_used=800`、`user_remaining=200`。
- 再传 800 字节返回 413，原因含「上传总量」。
- 另一个上传者额度独立，不受影响。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/config.py` | `max_user_bytes`（`COURSEBOX_MAX_USER_BYTES`） |
| `app/api/files.py` | `upload_quota`/`upload_allowance` 增 `user_id`；统计与候选；返回 user_* |
| `app/schemas.py` | `CourseQuota` 补 `user_limit/user_used/user_remaining` |
| `static/app.js` | 配额提示补「我的上传剩余」 |
| `tests/test_files.py` | 新增 `test_per_user_upload_quota` |
| `.env.example`、`README.md` | 同步 |

验证：`ruff` 全绿，`pytest` 146 passed（第十二轮 145 → 146）。
