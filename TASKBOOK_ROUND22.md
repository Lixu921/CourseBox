# CourseBox 第二十二轮任务书：保持唤醒与数据持久化

## 背景

线上跑在 Render 免费实例上，两个已知代价：闲置约 15 分钟会休眠（冷启动约 50 秒），
以及免费盘是临时的（重启/重新部署会丢库与上传）。本轮把这两点的应对做成可操作的东西。

## 项目

| 编号 | 主题 | 做法 |
| --- | --- | --- |
| P1 | 保持唤醒 | 新增 `.github/workflows/keepalive.yml`：每 5 分钟访问一次 `/api/health`，冷启动时自动重试直到唤醒。文档另给出 UptimeRobot / cron-job.org 的更可靠替代 |
| P2 | 数据持久化 | **不写死磁盘**（免费实例加 disk 会导致部署失败），改为在 `render.yaml` 加注释说明、在 `DEPLOY.md` 写清步骤：升级付费实例 → 挂载 `/var/data` → 把 `COURSEBOX_DB`/`COURSEBOX_UPLOAD_DIR` 指过去；并给出「自建 VPS + docker-compose」这条更稳的路 |

## 为什么 P2 不直接改 render.yaml 生效

Render 的持久磁盘只支持付费实例类型；在免费服务上声明 `disk:` 会让 Blueprint 应用失败，
反而把正在跑的站点弄挂。所以只放「注释示例 + 文档步骤」，由你按需启用。

## 验收

- `keepalive.yml` 语法正确，手动触发（workflow_dispatch）能访问健康接口。
- `DEPLOY.md` 含「保持唤醒」「Persist data」两节，步骤可照做。
- `render.yaml` 仍能用于免费部署（磁盘部分仅注释）。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `.github/workflows/keepalive.yml` | 新增定时唤醒工作流 |
| `DEPLOY.md` | 新增「Keep the free instance awake」「Persist data」 |
| `render.yaml` | 加磁盘/路径的注释示例（不默认启用） |
| `README.md` | 在线访问说明补充唤醒与持久化指引 |

验证：本轮不改应用代码，`ruff` 全绿；可用 `workflow_dispatch` 手动跑一次 keepalive 验证。
