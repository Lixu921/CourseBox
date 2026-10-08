# CourseBox 第九轮任务书：健康检查缓存与审计游标分页

## 背景

第八轮把「运行期整洁」的三项里先做了 A1–A3，A4（游标分页）与 A5（健康检查降频）留到本轮，
A6（乐观锁）继续暂缓。

## 执行约定

与第七、八轮一致：只改本仓库、每项独立验收、提交前 `ruff` 与 `pytest` 全绿、接口保持向后兼容。

## 项目

| 编号 | 主题 | 做法 |
| --- | --- | --- |
| A5 | 健康检查结果缓存 | 新增 `COURSEBOX_HEALTH_CACHE_SECONDS`（默认 10，0 表示关闭）。`/接口/健康` 在 TTL 内直接回缓存，避免监控高频触发整库 `PRAGMA quick_check`。缓存 key 由「库路径 + 上传目录 + 磁盘下限」组成，换了配置就重新体检；`reset_health_cache()` 供测试清空 |
| A4 | 审计游标分页 | `/接口/审计` 新增可选 `游标`（整数，返回编号更小的记录）。审计是持续追加的表，按 offset 翻页会在新增记录时跳条/重复；客户端把上一页最后一条的 `id` 作为下一页游标。原 `page`/`page_size` 保持不变 |

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- A5：同一配置下连续两次 `/接口/健康` 只真正查库一次；把缓存秒数设为 0 时两次都查。
- A4：第一页后取最后一条 id 作游标，第二页的记录全部严格更小且与第一页不相交；`游标=0` 返回 422。

## 完成情况

| 编号 | 状态 | 落点 |
| --- | --- | --- |
| A5 | 完成 | `app/config.py`（`health_cache_seconds`）、`app/main.py`（`_health_cache`/`reset_health_cache`/`run_health_checks`）、`tests/conftest.py` 重置缓存 |
| A4 | 完成 | `app/api/audit.py` 的 `list_audit_logs` 新增 `游标` |

验证：`ruff` 全绿，`pytest` 139 passed（第八轮 136 → 139）。

## 仍暂缓

- **A6 乐观锁**：编辑课程/资料标题加版本号，冲突返回 409。会引入表结构变更（`updated_at`）
  与前端交互，留待单独一轮。
