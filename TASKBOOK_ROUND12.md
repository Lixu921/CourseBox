# CourseBox 第十二轮任务书：CI 冒烟、依赖审计与 compose 持久化

## 背景

前几轮把代码层面的缺口补得差不多了。这一轮转向「跑起来才算数」和「运维便捷」：
CI 目前只用 TestClient，绕过了真实 HTTP 栈；依赖没有安全扫描；容器跑起来数据落在临时层。

## 项目

| 编号 | 主题 | 做法 |
| --- | --- | --- |
| O1 | 真实服务冒烟 | 新增 `scripts/smoke.py`（仅标准库）：对已启动的服务检查健康、首页、课程列表、OpenAPI、未授权 401、未知接口 404 JSON、浏览器错误页。CI 新增 `smoke` 任务：起真实 `uvicorn` 后执行它 |
| O2 | 依赖安全扫描 | `requirements-dev.txt` 加 `pip-audit`；CI 在 3.14 腿跑 `python -m pip_audit`，先 `continue-on-error`（只报告不阻断），稳定后再收紧 |
| O3 | 单机编排持久化 | 新增 `docker-compose.yml`：命名卷挂载 `/app/data` 与 `/app/uploads`，容器重建不丢数据；非 root 镜像沿用第十一轮的 Dockerfile |

## 为什么冒烟值这个价

TestClient 直接调用 ASGI app，绕过真实的中间件顺序与路由匹配。历史上两处只在真实服务上
才暴露的问题都印证了这点：

- 批量审核写成 `PATCH` 被 `PATCH /接口/资料/{编号}` 抢先匹配 → 422；
- 分块请求体的 413 因中间件层次不对，被 `BaseHTTPMiddleware` 吞成 400。

冒烟脚本本身就抓到了第三个：最初把 OpenAPI 定义写成 `/接口/定义`，实际路由是 `/接口定义`
（无斜杠），只有起真实服务才一眼看穿。

## 验收

```powershell
py -m ruff check .
py -m pytest

# 另开一个终端起服务后：
py scripts\smoke.py --base-url http://127.0.0.1:8000
```

- `smoke.py` 对全部检查输出 `ok` 并以 0 退出；任何一项失败输出 `FAIL` 并以 1 退出。
- compose 文件语法正确（`docker compose config`），卷挂载到数据与上传目录。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `scripts/smoke.py` | 新增，仅标准库 |
| `.github/workflows/ci.yml` | 新增 `smoke` job；`check` 的 3.14 腿加 `pip-audit`（非阻断） |
| `docker-compose.yml` | 新增，命名卷持久化 |
| `requirements-dev.txt` | 加 `pip-audit` |
| `README.md`、`DEPLOY.md` | 补充冒烟与 compose 用法 |

验证：`ruff` 全绿，`pytest` 145 passed（本轮不新增 pytest 用例，改动在 CI 与运维层）；
`scripts/smoke.py` 本地对真实 uvicorn 跑通，退出码 0。
