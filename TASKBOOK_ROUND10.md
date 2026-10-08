# CourseBox 第十轮任务书：编辑乐观锁

## 背景

课程与资料标题的编辑一直是「后写覆盖」：两人同时打开编辑，后保存的人会静默冲掉前者
的修改，谁都不会收到提示。本轮加上乐观锁，把冲突显式化。

## 设计

- `courses` 与 `files` 各加一列 `version INTEGER NOT NULL DEFAULT 1`（结构版本升到 v5）。
- 新增/编辑响应里带出 `version`；编辑请求可带 `version`（客户端看到并基于其编辑的版本号）。
- 服务端在更新前比对：带了的版本号与库里不一致 → `409`（`error.code = conflict`），
  并提示「已被他人修改，请刷新后重试」。更新成功时 `version + 1`。
- **向后兼容**：不传 `version` 时保持原来的「后写覆盖」，旧客户端不受影响。
- 前端在课程编辑、资料标题编辑（课程页与「我的上传」两处）回传当前版本号；命中 409 时
  现有的错误提示会把服务端消息弹出来。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 带正确版本号编辑成功且 `version` 递增；带过期版本号返回 409 且数据未被覆盖；不传版本号仍然成功。
- 老库（无 `version` 列）跑一次 `init_db` 自动补列并把 `user_version` 升到 5。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/db.py` | `courses`/`files` 建表加 `version`；`migrate_files_table`、新增 `migrate_courses_table` 补列；`SCHEMA_VERSION = 5` |
| `app/schemas.py` | `Course.version`；`CourseUpdate.version`、`FileUpdate.version`（可选，`ge=1`） |
| `app/api/courses.py` | 各 SELECT 带出 `version`；`update_course` 比对后 `version + 1`，冲突 409 |
| `app/api/files.py` | `file_response` 透出 `version`；相关 SELECT 补列；`update_file` 比对后 `version + 1`，冲突 409 |
| `static/app.js` | 三处编辑请求回传 `version` |
| `tests/test_courses.py`、`tests/test_files.py` | 各加一条乐观锁用例；更新既有期望值 |

验证：`ruff` 全绿，`pytest` 141 passed（第九轮 139 → 141）。

至此第七至第十轮的复审项全部落地：R1–R12、A1–A6。
