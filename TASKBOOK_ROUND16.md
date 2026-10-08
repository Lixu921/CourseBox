# CourseBox 第十六轮任务书：OpenAPI 本地化重写

## 背景

接口文档的中文名一直是在 `app/main.py` 里对生成的 OpenAPI 做后处理。旧实现有两个问题：

1. **`$ref` 用子串替换**：`#/components/schemas/Course` 会先把 `CourseCreate` 命中，改成
   「课程Create」，后续规则再也匹配不上——给模型改名时中文名会静默出错。
2. **覆盖不全**：本地化表停留在早期模型，新增的 `ShareLink`/`ShareView`/`CourseQuota` 等
   在文档里仍是英文标题，且没有测试看住。

本轮重写，不改运行时行为，只让这段更正确、更好维护，并补齐新模型。

## 设计

- 把映射拆成三张显式表：
  - `OPENAPI_SCHEMA_TITLES`：模型名 → 中文（补齐 Share*/CourseQuota/Trash*/Audit*/Batch* 等）。
  - `OPENAPI_PATH_PARAM_TITLES`：路径参数 `course_id`/`file_id`/`share_id`/`token`/`coursebox_session`。
  - `OPENAPI_PROPERTY_TITLES`：属性标题（补 tags、user_*、days、note、token、url、expires_at 等）。
- `$ref` 改为**按组件全名精确映射**：取 `#/components/schemas/` 之后的完整名字再查表，杜绝子串误伤。
- 路径、引用、schema 三步各自独立函数，逻辑一眼可读。

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 组件里有「课程」「课程创建请求」「分享链接」「分享内容」，没有 `Course`/`ShareLink` 残留。
- `分享内容.properties.course.$ref` 精确等于 `#/components/schemas/课程`（未被 `CourseCreate` 误伤）。
- 路径参数全部中文化；`课程.properties.tags.title == "标签"`、`分享链接.properties.token.title == "令牌"`。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/main.py` | 三张映射表 + `_localize_paths`/`_localize_references`/`localized_openapi` 重写 |
| `tests/test_platform.py` | 新增 `test_openapi_localization_is_robust` |
| `README.md` | 「已知局限」相应更新 |

验证：`ruff` 全绿，`pytest` 150 passed（第十五轮 149 → 150）。
