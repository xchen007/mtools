# Jira Workspace 交接文档

Current-state note, 2026-06-14: this handoff is historical and no longer reflects the current completion state. Use `docs/superpowers/plans/STATUS.md` and `README.md` for current routes, navigation, data freshness notes, and verification status.

日期：2026-06-12

## 1. 当前状态

- 当前分支：`master`
- 当前 HEAD：`43915ed8e56555d8920a64210a9e7f79a56c182a`
- 目标：将 `/Users/xchen17/workspace/mjira` 的 Jira 查询与同步能力迁入 `mtools`，落成 Django app `apps/jira_workspace`

当时整体进度（历史记录，已被后续实现覆盖）：

- Task 1 已完成：Jira app 骨架、路由、基础测试
- Task 2 已完成：本地缓存模型、迁移、模型测试
- Task 3 当时基本实现完成，但代码质量审查未通过，尚未最终收口
- Task 4-7 当时尚未开始正式实现。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

## 2. 已完成内容

### 2.1 文档

- 设计文档：`docs/superpowers/specs/2026-06-11-jira-workspace-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-11-jira-workspace-implementation.md`

### 2.2 Jira app 骨架

已创建：

- `apps/jira_workspace/__init__.py`
- `apps/jira_workspace/apps.py`
- `apps/jira_workspace/urls.py`
- `apps/jira_workspace/views.py`
- `apps/jira_workspace/tests/test_app_boot.py`
- `apps/__init__.py`

已接入：

- `mtools/settings.py`
- `mtools/urls.py`

### 2.3 数据模型与迁移

已创建模型：

- `JiraIssue`
- `JiraIssueMetric`
- `JiraSyncProfile`
- `JiraSyncRun`
- `JiraSavedQuery`

已创建迁移：

- `apps/jira_workspace/migrations/0001_initial.py`

已落实的 schema 约束：

- `JiraSyncProfile.is_default=True` 通过条件唯一约束保证全库最多一个默认 profile

### 2.4 本地查询与统计服务

已创建：

- `apps/jira_workspace/services/query_service.py`
- `apps/jira_workspace/services/stats_service.py`
- `apps/jira_workspace/tests/test_query_service.py`

当前已实现能力：

- 按 `source=assigned|created|all` 过滤
- 按 `project_key` 过滤
- 按 `start/end` 过滤 `updated_at`
- 按关键字搜索 `issue_key/summary`
- 按 `sort_by/sort_order` 排序
- Dashboard 项目聚合分成：
  - `assigned`
  - `created`

## 3. 当前测试结果

已执行：

```bash
python manage.py test apps.jira_workspace.tests -v 1
```

结果：

- `10` 个测试全部通过

当前测试文件：

- `apps/jira_workspace/tests/test_app_boot.py`
- `apps/jira_workspace/tests/test_models.py`
- `apps/jira_workspace/tests/test_query_service.py`

## 4. 当时未收口问题

Task 3 的代码质量审查当时明确指出以下问题，当时尚未修复：

1. `build_issue_queryset()` 对 `sort_by` 没有白名单校验，非法字段会直接在 `order_by()` 触发 `FieldError`
2. `build_issue_queryset()` 对未知 `source` 值没有显式处理，当前会静默落到 `all` 分支，可能扩大结果集并掩盖调用方错误
3. `test_query_service.py` 覆盖面不足，尚未覆盖：
   - `start/end`
   - `search`
   - `sort_by/sort_order`
   - 非法输入
   - 聚合数量与排序

结论：

- 当时 Task 3 功能上可用，但从服务契约和回归保护角度看，还不能视为最终完成。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

## 5. 与 mjira 对照后的关键信息

已确认 `mjira` 中相关文件位置：

- `/Users/xchen17/workspace/mjira/src/mjira/jira_adapter.py`
- `/Users/xchen17/workspace/mjira/src/mjira/services/query_service.py`
- `/Users/xchen17/workspace/mjira/src/mjira/services/sync_service.py`
- `/Users/xchen17/workspace/mjira/src/mjira/models.py`
- `/Users/xchen17/workspace/mjira/tests/test_query_service.py`
- `/Users/xchen17/workspace/mjira/tests/test_sync_service.py`

已确认差异：

- `mjira` 的 `jira_adapter.py` 使用的是 `jira` Python SDK
- 当前 `mtools` 虚拟环境里：
  - `django` 已安装
  - `requests` 已安装
  - `jira` 未安装

这意味着后续真实数据对接有两条路：

1. 延续当前计划，用 `requests` 直接封装 Jira REST API
2. 明确引入 `jira` SDK，并尽量贴近 `mjira` 的 adapter 实现

当前还没有进入这一步的最终实现。

## 6. 真实 Jira 对接前提

Jira 连接现在通过前端管理界面的 Jira Connection 配置保存，不再依赖 shell 环境变量。

真实 Jira 对接的前置工作主要是：

- 先修 Task 3 的服务参数校验
- 再实现 Task 4 的 adapter + sync service
- 然后补真实同步测试与最小联调验证

## 7. 当前工作区状态

`git status --short` 当前显示：

- `?? .claude/`
- `?? .superpowers/`
- `?? docs/superpowers/plans/`

说明：

- `.claude/`、`.superpowers/` 是会话和预览产物，不应随功能代码一起提交
- `docs/superpowers/plans/2026-06-11-jira-workspace-implementation.md` 目前仍未纳入 git 跟踪

## 8. 建议的下一步

建议按下面顺序继续：

1. 修 Task 3
   - 给 `source` 做显式枚举校验
   - 给 `sort_by` 做白名单校验
   - 扩充 `test_query_service.py`
2. 开始 Task 4
   - 决定 adapter 技术路线：`requests` 还是 `jira` SDK
   - 迁移 `mjira` 的增量同步逻辑到 Django 模型
   - 写 `test_sync_service.py`
3. 再做 Task 5
   - Dashboard 页面
   - 时间范围控件
   - 异步 ticket table 刷新
4. 最后做 Task 6-7
   - Saved Queries
   - Profiles & Sync
   - 页面联调与整体验证

## 9. 关键提交

- `25b558b` `Add Jira workspace design spec`
- `8db1320` `feat: scaffold jira workspace app`
- `da1e6c0` `test: cover jira workspace app installation`
- `b3b1df8` `test: enable package-level app test discovery`
- `a0c613a` `feat: add jira workspace data models`
- `ec83b8b` `fix: enforce single default jira sync profile`
- `beaf55c` `feat: add jira workspace query services`
- `43915ed` `test: cover jira workspace source query semantics`

## 10. 一句话交接结论

当时已经把 Jira Workspace 的 Django 骨架、本地数据模型和第一版查询/统计服务落下来了，测试是绿的；但查询服务的参数校验和测试覆盖还不够，真实 Jira 数据对接尚未开始。该结论已被后续实现覆盖，当前状态请以 `docs/superpowers/plans/STATUS.md` 和 `README.md` 为准。
