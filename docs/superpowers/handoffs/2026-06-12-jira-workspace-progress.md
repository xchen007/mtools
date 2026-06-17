# Jira Workspace 进度交接

Current-state note, 2026-06-14: this progress handoff is historical and no longer reflects the current completion state. Use `docs/superpowers/plans/STATUS.md` and `README.md` for current routes, navigation, data freshness notes, and verification status.

日期：2026-06-12
仓库：`/Users/xchen17/workspace/mtools`
分支：`master`
当前提交：`26474d7`
当时状态（历史记录，已被后续实现覆盖）：Task 1-3 已完成且测试稳定；Task 4 已实现但存在真实代码质量阻塞，尚未进行 live validation；Task 5-7 当时尚未开始。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

## 1. 交接结论

当前仓库已经不是“只有设计和页面草图”的阶段，而是已经落地了 Jira Workspace 的 Django 后端骨架、本地数据模型、查询/统计服务，以及第一版真实 Jira adaptor / sync 服务。

截至这次交接，可以把状态准确理解为：

- `Task 1` 已完成并稳定
- `Task 2` 已完成并稳定
- `Task 3` 已完成并收口，之前 review 指出的输入校验缺口已修补，本地测试全绿
- `Task 4` 已实现并有 mocked tests，但代码质量审查已指出 4 个真实问题，当前不应直接视为可上线或可做正式 live validation
- `Task 5-7` 当时尚未开始。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

## 2. 参考文档

- 设计文档：`docs/superpowers/specs/2026-06-11-jira-workspace-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-11-jira-workspace-implementation.md`

## 3. 已完成内容

### 3.1 Task 1：Django app 骨架与路由

已完成：

- 新建 `apps/jira_workspace/`
- 接入 `mtools/settings.py`
- 接入 `mtools/urls.py`
- 增加基础 dashboard 路由
- 增加 app boot 测试
- 修复包级测试发现问题

相关提交：

- `8db1320` `feat: scaffold jira workspace app`
- `da1e6c0` `test: cover jira workspace app installation`
- `b3b1df8` `test: enable package-level app test discovery`

### 3.2 Task 2：本地 Jira 数据模型与迁移

已完成：

- 新建模型：
  - `JiraIssue`
  - `JiraIssueMetric`
  - `JiraSyncProfile`
  - `JiraSyncRun`
  - `JiraSavedQuery`
- 新建初始迁移 `apps/jira_workspace/migrations/0001_initial.py`
- 注册到 Django admin
- 补齐模型测试
- 增加数据库级条件唯一约束：仅允许一个默认 sync profile

当前 profile scope 以更通用的三类为准：

- `my_issues`
- `project`
- `custom_jql`

注意：当前不再需要 `team profile`。

相关提交：

- `a0c613a` `feat: add jira workspace data models`
- `ec83b8b` `fix: enforce single default jira sync profile`

### 3.3 Task 3：查询 / 统计服务迁移

已完成：

- 新建 `apps/jira_workspace/services/query_service.py`
- 新建 `apps/jira_workspace/services/stats_service.py`
- 新建 `apps/jira_workspace/tests/test_query_service.py`
- 将 `mjira` 的本地查询 / 统计思路迁入 Django ORM

已落地语义：

- `assigned` => `assignee = username`
- `created` => `reporter = username`
- `all` => `assignee = username OR reporter = username`

已支持查询参数：

- `project_key`
- `start`
- `end`
- `search`
- `sort_by`
- `sort_order`

已补齐的输入收口：

- `source` 白名单校验
- `sort_by` 白名单校验
- `sort_order` 白名单校验
- `summary` 已加入允许排序字段

已补齐的测试覆盖：

- assigned / created / all 三种 source 语义
- 时间范围过滤
- 搜索过滤
- `project_key` 过滤
- 正向排序
- 非法 `source`
- 非法 `sort_by`
- 非法 `sort_order`
- dashboard 项目分组计数与顺序

相关提交：

- `beaf55c` `feat: add jira workspace query services`
- `43915ed` `test: cover jira workspace source query semantics`
- `1eb433c` `fix: validate jira workspace query inputs`
- `26474d7` `test: close jira workspace query service gaps`

### 3.4 Task 4：真实 Jira adaptor / sync 服务

已完成：

- 新建 `apps/jira_workspace/services/jira_adapter.py`
- 新建 `apps/jira_workspace/services/sync_service.py`
- 新建 `apps/jira_workspace/tests/test_sync_service.py`
- 在 `mtools/settings.py` 中接入 Jira 环境变量读取
- 采用 `requests` 方案，没有引入 `jira` SDK

当前已实现能力：

- `/rest/api/2/myself`
- `/rest/api/2/search`
- search 分页拉取
- issue payload 归一化
- `my_issues` / `project` / `custom_jql` 三类 profile 的 JQL 生成
- `full_sync(profile)`
- `incremental_sync(profile)`
- `JiraSyncRun` success / failed 记录
- `profile.last_cursor` 持久化
- 保留基础 JQL，不把 cursor 扩展后的 JQL 回写到 profile

当前已归一化并落库的主要字段：

- `issue_key`
- `project_key`
- `summary`
- `status`
- `assignee`
- `reporter`
- `priority`
- `sprint`
- `updated_at`
- `created_at`
- `raw_json`

相关提交：

- `c3ac125` `Add Jira sync adapter and service`

## 4. 当前关键代码位置

App / 路由：

- `apps/jira_workspace/apps.py`
- `apps/jira_workspace/urls.py`
- `apps/jira_workspace/views.py`
- `mtools/settings.py`
- `mtools/urls.py`

模型：

- `apps/jira_workspace/models.py`
- `apps/jira_workspace/migrations/0001_initial.py`

查询 / 统计：

- `apps/jira_workspace/services/query_service.py`
- `apps/jira_workspace/services/stats_service.py`
- `apps/jira_workspace/tests/test_query_service.py`

真实 Jira 对接 / 同步：

- `apps/jira_workspace/services/jira_adapter.py`
- `apps/jira_workspace/services/sync_service.py`
- `apps/jira_workspace/tests/test_sync_service.py`

## 5. 当前测试状态

本地完整测试已再次实跑通过。

执行命令：

```bash
.venv/bin/python manage.py test apps.jira_workspace.tests -v 2
```

本次结果：

- `22` 个测试全部通过
- Django system check 无报错

通过的测试组：

- `test_app_boot.py`
- `test_models.py`
- `test_query_service.py`
- `test_sync_service.py`

## 6. Task 3 最终判断

Task 3 当前可以视为已收口。

原因：

- 之前明确存在的两个真实问题已经修掉：
  - `source` 未做显式校验
  - `sort_by` 未做白名单校验
- 同时补上了：
  - `sort_order` 白名单
  - `summary` 排序支持
  - 对应测试覆盖
- 当前仓库状态和测试结果一致，没有残留的已知 Task 3 缺口

注意：

- 这并不等于“永远无需再动 Task 3”
- 只是说明按当前计划范围，Task 3 已不再是阻塞项

## 7. Task 4 代码质量审查结论

Task 4 的实现已经在仓库中，但代码质量审查给出了 4 个真实问题。
这些问题没有被证伪，因此 Task 4 当前不能直接视为 ready。

### 7.1 `custom_jql` 的增量 JQL 拼接不安全

问题位置：

- `apps/jira_workspace/services/sync_service.py`

当前做法：

- `_append_updated_clause()` 通过查找字面量 `" order by "`，再拼接 `AND updated >= ...`

风险：

- `ORDER BY` 若是多行或格式化写法，当前分割可能失效
- 原始自定义 JQL 若包含 `OR`，直接追加 `AND updated >= ...` 会改变语义
- 缺少对 base JQL 的显式括号包裹

影响：

- `custom_jql` profile 的增量同步结果可能错误

### 7.2 用户身份语义不一致

问题位置：

- `apps/jira_workspace/services/jira_adapter.py`
- `apps/jira_workspace/services/sync_service.py`

当前做法：

- `fetch_current_user()` 优先取 `name / key / accountId / emailAddress`
- issue 归一化时，用户字段优先取 `name / displayName / emailAddress / accountId`

风险：

- 远端 JQL 使用的“当前用户标识”与本地落库的用户标识可能不一致
- 在 Jira Cloud 或隐私收紧的 tenant 下尤其容易漂移

建议方向：

- `my_issues` JQL 更适合直接使用 `currentUser()`
- 本地归一化和远端查询语义需要统一

### 7.3 同步不会回收已经脱离 profile 范围的 issue

问题位置：

- `apps/jira_workspace/services/sync_service.py`

当前做法：

- `_store_items()` 只处理本次 fetch 回来的 issue
- 对已经不再匹配 profile 的旧 issue 没有清理或标记逻辑

风险：

- issue 被改项目、改 assignee、改 reporter，或不再匹配 custom JQL 后，本地缓存会残留脏数据

需要决策的方向：

- 按 profile 做 last-seen / stale 标记
- 或做 profile 作用域下的显式 reconciliation

### 7.4 adapter / sync 测试覆盖还不够强

问题位置：

- `apps/jira_workspace/tests/test_sync_service.py`

当前情况：

- 现有测试大多 mock 了 adapter
- 对 adaptor 层本身的 request / auth / pagination / normalization 行为覆盖不足

还缺的重点测试：

- request 参数和认证头是否正确
- search 分页是否按预期迭代
- normalization 是否覆盖多种 Jira payload 形态
- failed run 是否正确记录
- 下发到 adapter 的 JQL 是否与预期完全一致

## 8. 当前环境与真实接入前提

Jira 连接现在通过前端管理界面的 Jira Connection 配置保存，不再依赖 shell 环境变量。

当前实现路线已经明确：

- 使用 `requests`
- 不补 `jira` SDK

执行 Django 命令时，应使用：

```bash
.venv/bin/python manage.py ...
```

不要默认使用系统 `python`。

## 9. 当时尚未开始的任务

### 9.1 Task 5：Dashboard 页面

当时尚未开始。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

后续目标应对齐当前已经讨论过的产品语义：

- dashboard 默认只看我自己的 ticket
- 默认时间范围为最近 15 天滚动窗口
- 默认按最近更新时间排序
- 同时展示：
  - `Assigned To Me`
  - `Created By Me`
- 项目分组需要保留来源语义：
  - 点 `Assigned To Me` 下的项目，只看 `assignee = me`
  - 点 `Created By Me` 下的项目，只看 `reporter = me`
- 点击 project 后，右侧 ticket 表格异步刷新
- ticket 表格区域需要比左侧更宽

### 9.2 Task 6：Saved Queries / Profiles & Sync 页面

当时尚未开始。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

后续目标：

- 支持通用自定义查询
- 可保存为命名 profile
- profile 中包含：
  - 类型
  - 参数
  - JQL
  - 同步游标
  - 最后同步时间
- 左侧具备搜索、收藏、快速切换的查询列表体验

### 9.3 Task 7：整体验证

当时尚未开始。当前状态请以 `docs/superpowers/plans/STATUS.md` 为准。

需要补：

- 页面路由 smoke tests
- 真实 sync 流程验证
- 导航 / partial / 页面响应验证
- 全量回归测试

## 10. 建议恢复顺序

建议按下面顺序继续，不要直接跳到前端页面：

1. 先修复 Task 4 的 4 个代码质量问题
2. 补 adapter / sync 测试
3. 重跑 `apps.jira_workspace.tests`
4. 对 Task 4 再做一次 code-quality review
5. 开始第一次真实 Jira live validation
6. 只有 live validation 通过后，再进入 Task 5 Dashboard 页面
7. 然后做 Task 6
8. 最后做 Task 7 整体验证

## 11. Live Validation 最小执行清单

建议首次真实验证只走最小路径：

1. 在 Django shell 中创建一个 `my_issues` profile
2. 调用 `SyncService().incremental_sync(profile)`
3. 检查：
   - `JiraIssue` 是否成功落库
   - `JiraSyncRun` 是否写入 success / failed
   - `profile.last_cursor` 是否更新
   - 最终发出的 JQL 是否符合预期
   - 用户身份语义是否与本地 dashboard 过滤口径一致
4. 再测一个 `project` profile
5. 最后再测一个 `custom_jql` profile

## 12. 当前工作区状态

当前未跟踪内容：

- `.claude/`
- `.superpowers/`
- `docs/superpowers/handoffs/`
- `docs/superpowers/plans/`

注意：

- 本次只生成和更新了交接文档，没有提交
- 提交时不要误把上述工作区噪音一并带上，除非明确要纳入版本控制

## 13. 一句话总结

Jira Workspace 的 Django 后端底座、查询服务和第一版真实同步服务都已经落地；当前真正的阻塞点不是“有没有代码”，而是 Task 4 的同步语义与可靠性还没收口，必须先修完再做真实 Jira 验证和后续页面实现。
