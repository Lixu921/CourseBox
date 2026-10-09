# CourseBox 第二十四轮任务书：课程名唯一、学院下拉、去掉学期

## 背景

三处改进：课程名不允许重复创建、创建课程时学院可从中国石油大学（华东）官网的学院列表里选、
不再需要「学期」字段（第二十三轮的「应急管理员找回」已作废撤销，编号跳过）。

## 学院名单来源

取自中国石油大学（华东）官网「教学科研单位」（`https://www.upc.edu.cn/`）中的教学学院。
前端用 `<input list>` + `<datalist>` 做成「可选可填」的组合框；后端 `college` 仍是自由文本，
所以不在列表里的学院也能填。

## 项目

| 编号 | 主题 | 做法 |
| --- | --- | --- |
| G1 | 课程名不重复 | 创建/改名时先查重 → 409；并建 `idx_courses_name_unique` 唯一索引兜住并发（老库若有重名，建索引失败则跳过，改由应用层查重） |
| G2 | 学院下拉 | 创建课程表单的学院改为 `datalist` 组合框，列出官网各学院，仍可手填 |
| G3 | 去掉学期 | 从 `Course`/`CourseCreate`/`CourseUpdate`、各查询、CSV 导出、课程卡片、分享页、OpenAPI 标题里移除 `semester`；新库建表不再含该列（老库保留该列但不再使用） |

## 验收

```powershell
py -m ruff check .
py -m pytest
```

- 重复课程名创建 → 409；改名撞名 → 409。
- 课程响应、列表、详情、搜索、CSV、分享内容里都不再有 `semester`。
- 首页创建课程表单里学院是下拉候选、没有学期字段。

## 完成情况

| 落点 | 说明 |
| --- | --- |
| `app/db.py` | `courses` 建表去掉 `semester`；新增 `ensure_course_name_unique` |
| `app/schemas.py` | `Course`/`CourseCreate`/`CourseUpdate` 去掉 `semester` |
| `app/api/courses.py` | 去 semester；创建/改名查重 → 409 |
| `app/api/files.py` | 搜索/导出/列表去掉 semester与「学期」列 |
| `app/api/insights.py`、`app/api/share.py` | 去掉 semester |
| `app/main.py` | OpenAPI 属性标题去掉「学期」 |
| `static/index.html`、`app.js`、`app-2.js`、`share.js` | 学院 datalist、去学期 |
| `tests/test_courses.py`、`test_export.py` | 更新期望；新增课程名唯一用例 |
| `README.md` | 功能与用例数同步 |

验证：`ruff` 全绿，`pytest` 167 passed（撤销第二十三轮后 166 → 167）。
