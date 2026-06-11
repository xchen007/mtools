# mtools Jira 工作台设计文档

日期：2026-06-11  
状态：待实现前确认  
语言：中文（按当前沟通要求）

## 1. 背景与目标

当前目标是将 `/Users/xchen17/workspace/mjira` 中已有的 Jira 查询与同步能力，复刻并整合到 `mtools` 中，作为 `mtools` 内部的一个 Jira 功能模块，而不是独立应用。

本轮设计的重点不是继续扩展 `ui-preview` 静态演示页，而是明确未来正式实现时的：

- 页面信息架构
- 查询与同步的数据模型
- Dashboard 的默认行为
- Saved Queries 工作台的交互方式
- Profile 驱动的本地缓存同步机制

本设计以“先同步到本地库，再在本地查询、筛选、排序、分页”为核心架构，避免把 Jira 页面做成每次都直连远端 API 的薄壳页面。

## 2. 总体设计结论

### 2.1 功能定位

Jira 将作为 `mtools` 中的新 Django app 存在，使用 `mtools` 自身的 Django 数据库和迁移体系管理，不再维护独立 SQLite 数据库。

### 2.2 范围结论

第一阶段实现以下三个核心工作区：

1. `Dashboard`
2. `Saved Queries`
3. `Profiles & Sync`

### 2.3 查询架构结论

采用 `mjira` 的总体思路，但进行泛化：

- 先从 Jira 同步 issue 到本地 Django 数据库
- 再在本地完成筛选、排序、分页、聚合统计
- 同步范围由 `Saved Profiles` 驱动
- 支持的 profile 类型为：
  - `my_issues`
  - `project`
  - `custom_jql`

不单独实现 `team profile`。后续如果有团队场景，统一通过保存的 `custom_jql` 覆盖。

## 3. 信息架构

## 3.1 全局结构

Jira 区域最终采用两层导航思路，但 Dashboard 主体布局采用更偏向方案 B 的“宽结果区”组织方式：

- 最左侧保留一条窄的全局工具 rail，用于工具级导航
- Jira 自身保留二级工作区入口：
  - `Dashboard`
  - `Saved Queries`
  - `Profiles & Sync`
- Dashboard 主体采用更强调中部结果区的布局，让 ticket 表格区域更宽

这意味着：

- Jira 仍然是一个独立工作区，而不是仅有一个单页查询器
- 但 Dashboard 的核心阅读区域，按“左侧导航 + 右侧宽表格”的方向组织

## 3.2 Saved Queries 的定位

`Saved Queries` 是第二个核心工作区，不是 Dashboard 的附属抽屉。

它承担通用查询工作台职责：

- 支持自定义过滤
- 支持保存查询
- 支持加星
- 支持在左侧做搜索与快速切换
- 结果以类似 Grafana metric table 的方式展示
- 点击行后打开详情区，查看 `Overview / History / Links / Raw JSON`

## 4. Dashboard 设计

## 4.1 Dashboard 的定位

`Dashboard` 是默认落地页，但它不是“所有 Jira 数据的总控台”，而是**个人 Jira 工作台**。

它只围绕“我自己的 ticket”展开，强调：

- 最近编辑的 ticket
- 在选定时间范围内与我相关的项目
- 分派给我 / 我创建的 ticket 视角
- 快速切换项目并查看结果表

## 4.2 Dashboard 查询边界

Dashboard 只看“我的 ticket”，但为了支持不同交互视角，采用两层语义：

### 默认语义

Dashboard 总体范围是“与我相关的 ticket”，即围绕：

- `assignee = me`
- `reporter = me`

进行聚合与分组展示。

### 点击项目后的语义

左侧项目列表分为两组：

1. `Assigned To Me`
2. `Created By Me`

点击项目名后，右侧表格异步刷新，并**保留来源语义**：

- 如果从 `Assigned To Me` 组点击项目，只查 `assignee = me`
- 如果从 `Created By Me` 组点击项目，只查 `reporter = me`

不会在点击后自动退化成 `reporter = me OR assignee = me` 的混合集合。

## 4.3 时间过滤

Dashboard 顶部时间过滤样式按确认稿实现，采用如下格式：

- 快捷范围：`7d / 30d / 90d / 1y / All`
- 起始日期输入框
- 结束日期输入框

默认时间范围为：

- **最近 15 天滚动窗口**

该时间范围用于：

- 左侧项目聚合
- 最近更新 ticket 列表
- 右侧 ticket 表格刷新
- Dashboard 统计卡片

## 4.4 Dashboard 布局规则

Dashboard 主布局采用“左窄右宽”的组织方式：

### 左侧区域

左侧用于放置聚合与导航信息，主要包含：

- 当前时间范围下的项目列表
- `Assigned To Me` 项目组
- `Created By Me` 项目组
- 最近更新的 ticket 列表
- 个人统计卡片

### 右侧区域

右侧用于放置主 ticket 表格，并且**表格区域需要比之前方案更宽**。  
右侧表格是 Dashboard 的主阅读区域。

## 4.5 Dashboard 必须展示的信息

Dashboard 首屏至少需要包含：

- 时间过滤条
- 当前默认个人范围说明
- 选定时间内：
  - 分派给我的 ticket 所属项目
  - 我创建的 ticket 所属项目
- 最近更新的 ticket
- 右侧宽表格
- 默认按最近编辑时间排序的 ticket 列表

## 4.6 Dashboard 表格行为

右侧 ticket 表格需要满足：

- 默认排序：`updated desc`
- 支持异步刷新，不整页重载
- 支持根据左侧点击的项目立即刷新
- 在行级别至少展示：
  - issue key
  - summary
  - role（Reporter / Assignee）
  - status
  - project
  - updated time
  - priority

如果后续要扩展，还可以增加：

- sprint
- labels
- worklog
- raw payload 快速入口

## 5. Saved Queries 设计

## 5.1 Saved Queries 的目标

`Saved Queries` 用来承接“根据一堆自定义查询过滤出一些 ticket，然后显示出来，并长期复用”的场景。

它不是 Dashboard 的翻版，而是偏运维 / 观测 / 分析型的通用工作台。

## 5.2 Saved Queries 的核心能力

第一阶段要覆盖：

- Query 列表
- Query 搜索
- Query 加星
- Query 置顶 / pinned
- 绑定 Profile
- 自定义过滤条件
- 可保存的查询定义
- 结果表格展示
- 原始 JSON / 详情抽屉

## 5.3 Saved Queries 左侧区域

左侧区域类似“查询库”，用于放常用需求：

- 搜索已有 query
- 展示 starred queries
- 展示 pinned queries
- 快速切换当前 query

这一块应当具备类似 Grafana metric table 工作区的使用体验，即“常用查询集合 + 当前结果面板”。

## 5.4 Saved Queries 结果区

右侧结果区应支持：

- profile 切换
- 项目、状态、优先级、更新时间等过滤
- 自定义 JQL 或者等价过滤定义展示
- 查询指标摘要
- 结果表格
- 行点击后的详情抽屉

结果表格默认仍然可以按 `updated desc` 作为默认排序，但需要允许用户改排序字段。

## 6. Profiles & Sync 设计

## 6.1 Profiles 的意义

由于本设计采用“先同步到本地再查询”的架构，因此需要一个明确的同步范围定义机制。  
这里采用 `Saved Profiles`。

每个 Profile 都是一个可命名、可复用、可增量同步的范围定义。

## 6.2 Profile 类型

本轮确认的三种 Profile 类型：

1. `my_issues`
2. `project`
3. `custom_jql`

说明如下：

### `my_issues`

用于同步当前用户自己的 issue。  
JQL 自动生成，不需要用户手写。

### `project`

用于同步指定项目范围内的 issue。  
JQL 根据保存的 project key 自动生成。

### `custom_jql`

用于支持更通用和更灵活的查询范围。  
用户可以保存一段命名 JQL，之后复用、同步、查询。

## 6.3 Profile 持久化字段

每个 Profile 至少应保存：

- 名称
- 类型
- 参数
- 保存后的 JQL
- 是否默认
- 最近同步时间
- 增量同步 cursor
- 创建人 / 更新时间

## 6.4 Sync 语义

同步能力复刻 `mjira` 的逻辑，但不再只服务于单一 `my_issues` 场景，而是改成 profile 驱动。

支持：

- 全量同步
- 增量同步

每个 Profile 拥有各自独立的 cursor 和最近同步状态，不共享全局 cursor。

## 6.5 Profiles & Sync 页面职责

`Profiles & Sync` 页面承担以下职责：

- 查看 profile 列表
- 新建 / 编辑 / 删除 profile
- 设置默认 profile
- 手动触发全量同步
- 手动触发增量同步
- 查看最近同步运行记录
- 查看失败信息和错误摘要

## 7. 数据模型设计

所有数据并入 `mtools` 的 Django 数据库，由新 Jira app 的 `models.py` 与 migrations 管理。

## 7.1 JiraIssue

本地 issue 缓存模型，主要字段建议包括：

- `issue_key`
- `project_key`
- `summary`
- `status`
- `assignee`
- `reporter`
- `updated_at`
- `created_at`
- `sprint`
- `priority`
- `raw_json`
- `last_seen_at`

这里相较于 `mjira` 的最小模型，建议把 `reporter` 纳入正式字段，因为 Dashboard 已经明确需要区分：

- `assignee = me`
- `reporter = me`

## 7.2 JiraIssueMetric

扩展指标模型，用于后续统计和面板扩展。  
建议至少保留：

- `issue_key`
- `cycle_time_minutes`
- `worklog_minutes`
- `status_changed_at`

如果短期内没有数据来源，也可以先保留模型但不强依赖完整填充。

## 7.3 JiraSyncProfile

保存同步范围定义：

- `name`
- `profile_type`
- `is_default`
- `params_json`
- `jql`
- `last_cursor`
- `last_full_sync_at`
- `last_incremental_sync_at`
- `created_at`
- `updated_at`

## 7.4 JiraSyncRun

保存同步执行记录：

- `profile`
- `run_type`
- `started_at`
- `finished_at`
- `status`
- `fetched_count`
- `inserted_count`
- `updated_count`
- `skipped_count`
- `error_message`

## 7.5 JiraSavedQuery

保存常用查询定义：

- `name`
- `profile`
- `description`
- `filters_json`
- `jql_text` 或等价表达
- `is_starred`
- `is_pinned`
- `sort_by`
- `sort_order`
- `created_at`
- `updated_at`

## 8. 查询与同步流程

## 8.1 同步流程

同步流程的标准路径是：

1. 用户选择一个 `JiraSyncProfile`
2. 系统根据 profile 生成或读取 JQL
3. 调 Jira API 拉取 issue
4. 写入 / 更新本地 `JiraIssue`
5. 更新 profile 对应 cursor
6. 写 `JiraSyncRun`

## 8.2 查询流程

查询流程统一基于本地库：

1. 用户进入 Dashboard 或 Saved Queries
2. 页面根据当前 profile / 时间 / 项目 / 状态 / 关键字等参数拼装本地查询条件
3. 只查 Django 本地数据库
4. 返回：
   - 聚合统计
   - 项目分组
   - 最近更新列表
   - ticket 明细表格

## 8.3 Dashboard 查询规则

Dashboard 的核心查询规则如下：

- 时间范围默认最近 15 天
- 默认排序 `updated desc`
- 左侧按时间范围聚合：
  - `Assigned To Me` 项目
  - `Created By Me` 项目
- 点击左侧项目后：
  - 保留来源语义
  - 右侧表格异步刷新

## 9. 页面与服务落地建议

## 9.1 页面路由建议

建议至少提供以下路由：

- `/jira/dashboard/`
- `/jira/queries/`
- `/jira/profiles/`

## 9.2 服务层建议

建议从 `mjira` 迁移并调整出以下服务层：

- `jira_adapter`
- `sync_service`
- `query_service`
- `stats_service`

同时根据 Django 风格做适配，不保留 `mjira` 原有 SQLAlchemy 结构。

## 9.3 模板结构建议

前端风格沿用当前 `ui-preview` 的视觉方向，但落地到 Django 模板时应拆成可复用片段，例如：

- 全局 rail
- Jira workspace nav
- Dashboard 项目列表模块
- Ticket table
- 时间过滤条
- Query library
- Drawer / detail panel

## 10. 已确认的关键需求清单

本次沟通中已经明确确认的需求如下：

1. Jira 功能不是独立应用，而是整合进 `mtools`
2. 采用“先同步到本地，再做本地查询”的架构
3. 数据全部并入 `mtools` 的 Django 数据库
4. 使用 `Saved Profiles` 驱动同步范围
5. Profile 类型为：
   - `my_issues`
   - `project`
   - `custom_jql`
6. 不单独做 team profile
7. Jira 至少包含三个工作区：
   - Dashboard
   - Saved Queries
   - Profiles & Sync
8. Dashboard 只围绕“我的 ticket”
9. Dashboard 时间过滤样式采用：
   - `7d / 30d / 90d / 1y / All + 起止日期`
10. Dashboard 默认时间范围为最近 15 天滚动窗口
11. Dashboard 必须展示最近更新的 ticket
12. Dashboard 需要分别列出：
   - 过滤时间范围内 `Assigned To Me` 的项目
   - 过滤时间范围内 `Created By Me` 的项目
13. 点击项目名后，右侧 ticket 表格异步刷新
14. 点击项目后保留来源语义：
   - `Assigned To Me` 只查 `assignee = me`
   - `Created By Me` 只查 `reporter = me`
15. 右侧 ticket 表格区域要更宽
16. 右侧 ticket 表格默认按最近编辑时间倒序
17. Saved Queries 要具备类似 Grafana metric table 的查询工作台体验

## 11. 后续可调整项

本轮不把以下内容作为阻塞项，后续可以继续微调：

- Dashboard 统计卡片具体数量与样式
- Saved Queries 左侧是否加入更多搜索 / 收藏 / 标签管理
- Drawer 中是否增加更多字段
- 是否增加趋势图、项目排行等更重的管理型分析模块
- 是否支持更复杂的 bulk action 或自动化动作

当前目标是先把需求边界和实现骨架定清楚，再进入实现。
