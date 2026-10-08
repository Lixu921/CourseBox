# CourseBox 第十九轮任务书：并发一致性修复

## 背景

一次外部评审指出：几处「看起来有并发保护」的逻辑其实没有数据库层原子性，都是**先查后写**
（check-then-act），在高并发下会被覆盖或绕过。逐条核对属实，本轮修复并补并发回归测试。

## 修复项

| # | 问题 | 修复 |
| --- | --- | --- |
| C1 | 课程 / 资料乐观锁非原子：先 `SELECT version` 再 `UPDATE ... WHERE id=?`，并发时两请求都通过检查，版本 1→3、后写覆盖 | 把版本判断放进 `UPDATE ... WHERE id = ? AND version = ?`，用 `rowcount == 0` 判 409；未带版本时保持旧行为 |
| C2 | 「至少保留一个启用管理员」非原子：先 `count_active_admins()` 再更新，两个管理员同时降权/停用可清零 | 把计数子查询放进 `UPDATE ... WHERE id = ? AND (SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1) > 1`；`rowcount == 0` 判 409 |
| C3 | 上传配额非原子：先查 used 再 INSERT，并发上传可超限 | 改成条件 INSERT：`INSERT INTO files (...) SELECT ... WHERE <各配额剩余量仍满足>`，超限时 `rowcount == 0` 返回 413；磁盘余量仍走前置检查 |
| C4 | 备份非同一快照：先备份库、后打包上传目录，中间删除会「库有记录、归档缺文件」 | 代码层不改（单进程难做真快照），在 `app/backup.py` 文档与 README「已知局限 / 备份」写明：低峰或暂停写入时备份 |
| C5 | 课程编辑后前端短暂显示 `undefined 份已通过资料`：编辑接口返回普通 `Course`，被整体赋给 `currentCourse`，丢了 `file_count` | 改成合并 `currentCourse = { ...currentCourse, ...updated }` |

## 并发回归测试（`tests/test_concurrency.py`）

这些逻辑单请求测不出来，必须并发：

- **课程 / 资料编辑**：两个会话带同一版本号并发改，必须一个 200、一个 409，最终 `version == 2`。
- **管理员保留**：直接调 `apply_user_update` 并让两个连接都先读到「有两个管理员」再更新
  （走 HTTP 会因被降权方的鉴权时序而漂移），必须一个 200、一个 409，最终管理员数 == 1。
- **上传配额**：课程配额 10 字节、并发各传 8 字节，必须一个 201、一个 413，最终已用 == 8。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/api/courses.py` | `update_course` 版本判断入 `WHERE` |
| `app/api/files.py` | `update_file` 版本判断入 `WHERE`；新增 `quota_guard_clauses`，上传改条件 INSERT |
| `app/api/users.py` | 管理员保留改条件 `UPDATE`（子查询计数） |
| `static/app-2.js` | 课程编辑后合并而非覆盖 |
| `app/backup.py`、`README.md` | 备份快照局限写清 |
| `tests/test_concurrency.py` | 新增四条并发用例 |

验证：`ruff` 全绿，`pytest` 157 passed（第十八轮 153 → 157）。
