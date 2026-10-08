# CourseBox 第八轮任务书：运行期整洁

## 背景

第七轮修的是「看得见的缺陷」，这一轮处理「平时看不出、流量一大或长期运行才显形」的
三处：公开下载在数据库里写审计、搜索与列表可见性不一致、WAL 文件只涨不落。三条都做了
小改动、低风险，且各自带一条回归测试。

## 执行约定

- 只改本仓库；每项独立验收；提交前 `py -m ruff check .` 与 `py -m pytest` 全绿。
- 不改变现有 API 的请求/响应形状（搜索只是放宽已登录用户的可见范围）。

## 项目

| 编号 | 主题 | 现象 | 做法 |
| --- | --- | --- | --- |
| A1 | 公开下载不写审计 | 下载/预览/打包是公开接口，匿名请求也 `record_audit` + `commit`，被刷时 audit_logs 膨胀并制造写锁竞争 | 三个接口只在 `user is not None` 时写审计与提交 |
| A2 | 搜索可见性与列表一致 | 课程列表对上传者可见其待审资料，搜索却只回 `approved`；用户传完搜不到，以为丢了 | `search_files` 接入 `optional_user`，复用 `file_visibility`；前端搜索卡片给非通过项补状态徽标 |
| A3 | WAL 只涨不落 | 全仓库无 `PRAGMA wal_checkpoint`，长跑实例 `-wal` 可能持续增大 | 新增 `db.checkpoint_wal`，在启动维护与 `py -m app.maintenance` 各跑一次 `wal_checkpoint(TRUNCATE)` |

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- A1：匿名连下两次同一文件，`audit_logs` 中 `download` 计数为 0；登录用户下载后为 1。
- A2：匿名搜索待审资料为 0，上传者本人与管理员为 1，其他上传者为 0。
- A3：`checkpoint_wal` 在有效连接上执行不抛异常，数据不丢。

## 完成情况

| 编号 | 状态 | 落点 |
| --- | --- | --- |
| A1 | 完成 | `app/api/files.py`：`download_file`、`preview_file`、`download_course_archive` 改为登录才记审计 |
| A2 | 完成 | `app/api/files.py` 的 `search_files` 复用 `file_visibility`；`static/app.js` 的 `searchResultCard` 补状态徽标 |
| A3 | 完成 | `app/db.py` 新增 `checkpoint_wal`；`app/main.py`、`app/maintenance.py` 调用 |

验证：`ruff` 全绿，`pytest` 136 passed（原 133；新增 3 条回归）。未见「已知局限」需要改动。

## 暂缓（记在此，供后续轮次）

- **A4 keyset 分页**：审计/回收站等持续写入的表改游标分页，避免翻页跳条/重复。会动到
  `page` 语义与前端，单独一轮做。
- **A5 健康检查降频/缓存**：避免监控高频触发整库 `quick_check`。
- **A6 乐观锁**：编辑课程/资料加版本号，冲突返回 409。
