# mtools Workspace UI 全量迁移设计文档

Current-state note, 2026-06-14: this document is historical. The migrated routes still exist, but the visible Jira workflow has since converged on `/jira/query/` as a Query Card dashboard/workbench. `/jira/dashboard/`, `/jira/issues/`, and `/jira/sync/` are retained as compatibility/diagnostic backend pages, not primary visible navigation entries.

日期：2026-06-12
状态：待实现前确认
语言：中文

## 1. 背景

当前 `mtools` 中已经有一版可工作的 `jira_workspace` Django app，但它只覆盖了 Jira 的最小工作流页面，未将 `ui-preview/` 下的预览稿迁移为正式界面，也没有为 `sync2pod` 和 `integrations` 建立真实后端能力。

本轮目标不是继续维护静态 HTML 样稿，而是将以下预览页全部迁移为 Django 正式页面，并接入真实后端行为：

- `ui-preview/index.html`
- `ui-preview/dashboard.html`
- `ui-preview/jira-query.html`
- `ui-preview/jira-issues.html`
- `ui-preview/jira-sync.html`
- `ui-preview/sync2pod.html`
- `ui-preview/integrations.html`

用户已确认两点：

1. 预览稿是正式视觉和交互的基线
2. 非 Jira 页面也必须接真实后端能力，不能停留在 mock/demo

## 2. 目标与非目标

### 2.1 目标

1. 将 7 个预览页整合为一套共享的 Django workspace shell
2. 将所有目标页面接到正式路由，而不是停留在静态文件
3. 保持预览稿的信息层级、布局组织和主交互节奏
4. Jira 页面复用现有本地缓存与同步架构，补齐缺失页面能力
5. 为 `sync2pod` 新增真实服务层、运行记录与配置持久化
6. 为 `integrations` 新增真实目录/契约/就绪度聚合能力
7. 用测试覆盖新路由、服务层、错误态和关键写操作

### 2.2 非目标

1. 不引入单独的前端框架或 SPA 架构
2. 不为每个页面复制一份预览稿中的内联 CSS/JS
3. 不在本轮实现与设计无关的全局平台化重构
4. 不把 Jira 外部 403 阻塞问题伪装成代码已联通

## 3. 总体设计结论

采用“共享工作台壳层 + 功能页面模板 + 后端服务层”的 Django 服务端渲染架构。

### 3.1 共享壳层

新增统一 workspace base template，负责：

- 左侧导航
- 顶部搜索/命令/环境/用户栏
- 面包屑
- 右侧运行轨与状态区
- 全局视觉 token、布局网格、表格和面板样式

所有目标页面都继承这层壳，避免复制预览稿中的重复结构。

### 3.2 页面职责

正式路由定义如下：

- `/` -> redirect 到 `/workspace/`
- `/workspace/`
- `/jira/dashboard/`
- `/jira/query/`
- `/jira/issues/`
- `/jira/sync/`
- `/sync2pod/`
- `/integrations/`

页面职责如下：

- `workspace`：作为真实总览页，聚合 Jira、sync2pod、integrations 的最近运行、状态、入口与告警
- `jira/dashboard`：个人工作台，聚合统计、最近更新、项目维度结果区
- `jira/query`：保存查询、编辑过滤、执行查询、查询库浏览
- `jira/issues`：列表视图、筛选器、批量动作入口、详情侧栏
- `jira/sync`：同步 profile、同步触发、同步历史、运行状态
- `sync2pod`：配置管理、同步策略、执行控制、日志和观察信息
- `integrations`：工具目录、契约矩阵、就绪状态、引导接入流程

### 3.3 后端分层

页面只消费经过整理的 view context，不直接拼装底层行为。后端分为：

- `views`：协调请求、表单、分页、错误态
- `services`：Jira、sync2pod、integrations 的业务逻辑与外部系统交互
- `models`：本地持久化实体与运行记录
- `templates/partials`：可复用表格、列表、rail、指标区

## 4. 页面信息架构

## 4.1 全局工作台壳层

所有页面统一采用三栏布局基线：

- 左侧：工具级导航和当前 workspace 状态
- 中间：页面主内容
- 右侧：运行日志、任务队列、健康摘要、近期事件

布局可根据页面内容切换为双栏或压缩右栏，但导航语义保持一致。

### 左侧导航规则

左侧导航至少包含：

- Workspace
- Jira Dashboard
- Jira Query
- Jira Issues
- Jira Sync
- sync2pod
- Integrations

高亮规则由当前路由控制，不在模板中手写静态 active class。

### 顶部栏规则

顶部栏提供：

- 全局搜索/命令输入
- 页面级快捷动作按钮
- 环境标记
- 当前用户

不同页面可替换快捷动作按钮集合，但不替换整体结构。

### 右侧轨道规则

右侧轨道承担真实运行态信息展示：

- 最近运行
- 任务队列
- 健康指标
- 近期日志片段

如果当前功能暂无数据，也必须显示空态或缺失原因，不允许直接消失。

## 4.2 Workspace 页面

`/workspace/` 不再是设计说明页，而是正式入口页。

首屏需要展示：

- 各工具入口卡片
- 最近运行列表
- 跨工具健康状态
- 快速进入 Jira / sync2pod / integrations 的入口
- 当前阻塞项摘要

数据来源：

- Jira 同步记录与 issue 摘要
- sync2pod 运行记录
- integrations 目录摘要

## 4.3 Jira 页面组

Jira 四页共享统一二级语义，但拆成独立工作面：

### Dashboard

- 时间过滤
- 个人相关项目分组
- 最近更新 issue
- 主结果表
- 统计卡片

### Query

- 查询库
- profile 选择
- 可编辑查询条件
- 执行查询结果
- 查询指标摘要

### Issues

- 多维筛选
- 保存视图/标签式切换
- 结果列表
- 批量操作入口
- 详情侧栏

### Sync

- sync profile 列表
- profile 编辑表单
- full/incremental sync 触发
- 最近运行
- 错误与统计

现有 `queries`、`profiles` 页面不再作为最终信息架构保留，其能力将吸收进 `jira/query` 与 `jira/sync`。

## 4.4 sync2pod 页面

`/sync2pod/` 必须从样稿展示页升级为真实操作页。

页面需要覆盖：

- 配置列表与默认项
- 当前配置编辑
- 同步策略摘要
- 启动/取消执行
- 实时或准实时日志区域
- watch mode 队列
- archive/chunk/upload 进度与吞吐信息
- 排除规则与风险提示

这意味着需要真实的本地配置、运行记录和命令执行包装，而不是只渲染静态文案。

## 4.5 Integrations 页面

`/integrations/` 必须展示真实工具目录状态，而不是预览中的静态数组。

页面需要覆盖：

- 按组分类的工具目录
- 输入/输出/events 契约矩阵
- readiness 状态
- 最近目录刷新/扫描/接入事件
- 新工具接入引导入口

如果某个工具暂时没有完整契约，页面必须显示“缺失哪些字段”，而不是假定为 ready。

## 5. 数据与服务设计

## 5.1 Jira

Jira 继续沿用本地缓存查询架构，复用现有：

- `jira_adapter`
- `query_service`
- `stats_service`
- `sync_service`

需要补齐的能力：

1. 将 `queries`/`profiles` 视图重构为 `query`/`issues`/`sync` 三类页面上下文
2. 为 issues 页面提供更丰富的筛选、结果统计和详情数据
3. 为 sync 页面提供 profile 写入和触发动作
4. 为 workspace 总览输出 Jira 摘要 view model

Jira 的真实联调依旧依赖外部 Jira 服务；当前已知 403 阻塞需要以外部失败态展示。

## 5.2 sync2pod

仓库内当前没有现成 sync2pod Django 后端实现，因此本轮新增一组最小但真实的能力边界：

### 持久化实体

至少需要：

- `Sync2PodProfile`：本地路径、远端 pod/container/path、模式参数、排除项、是否默认
- `Sync2PodRun`：运行类型、状态、开始/结束时间、统计、错误信息、日志摘要
- `Sync2PodWatchEvent` 或等价结构：队列原因、触发时间、状态

### 服务层

至少需要：

- 配置 CRUD
- capability check
- 启动同步
- 取消同步
- 读取最近运行和日志摘要
- 组装页面指标

### 执行策略

优先采用仓库或本地可用的既有命令能力；如果没有统一封装，则新增一个 Python service 包装命令执行与结果持久化。

不要求本轮实现复杂的异步任务系统，但必须让页面能看到真实执行结果，而不是伪造状态。

## 5.3 Integrations

仓库内当前没有统一 registry，因此本轮新增轻量目录聚合层。

### 持久化与服务职责

至少需要：

- `IntegrationTool`：工具 key、名称、分组、readiness、描述
- `IntegrationContract`：输入/输出/events 支持情况与备注
- `IntegrationScanRun`：最近扫描/刷新记录

### 数据来源

初始阶段允许基于本地已知工具配置和代码可用性生成目录，但必须通过服务层统一输出，不允许在模板中写死数组。

### 页面行为

- 支持搜索
- 支持按组展示
- 支持 readiness/contract matrix 展示
- 支持展示最近刷新/扫描事件

## 6. 模板与静态资源设计

## 6.1 模板结构

新增或重构：

- 统一 workspace base template
- 页面模板：
  - workspace
  - jira dashboard
  - jira query
  - jira issues
  - jira sync
  - sync2pod
  - integrations
- partials：
  - left nav
  - topbar
  - right rail
  - kpi cards
  - ticket tables
  - run tables
  - query library
  - config list
  - contract matrix

## 6.2 样式策略

将预览稿里的视觉 token 抽到共享 CSS 中：

- 深色背景和面板层级
- 标题与等宽字体
- 边框、圆角、按钮、badge、表格
- 三栏/双栏布局

不保留预览稿中的每页内联 `<style>`。

## 6.3 前端脚本策略

继续使用轻量原生 JS，不引入框架。

JS 负责：

- 页面内异步刷新
- 过滤器和 tab 切换
- 局部表格/详情加载
- 运行状态轮询或刷新

JS 不负责承载核心业务逻辑，业务逻辑保留在 Django service 层。

## 7. 错误处理与阻塞态

## 7.1 Jira 外部阻塞

已知真实 Jira 请求当前会返回 403 和 `The request is blocked.`。

这类错误视为外部阻塞，不视为本地代码未完成，但页面必须：

- 清楚显示失败原因
- 保留已同步本地数据浏览能力
- 保留操作入口和最近运行记录

## 7.2 sync2pod / integrations 缺失依赖

如果本地命令、配置或扫描源缺失，页面必须显示：

- 当前缺什么
- 哪个功能受影响
- 哪些内容仍然可浏览

不允许出现空白页或 500。

## 8. 测试与验证

## 8.1 自动化测试

至少覆盖：

1. 新路由可达
2. 页面上下文构造正确
3. Jira 查询、同步、错误态
4. sync2pod 配置与运行记录行为
5. integrations 目录聚合与矩阵输出
6. 关键写操作表单

## 8.2 页面验收

手工验收目标为：

- 7 个正式页面都能打开
- 样式结构与 `ui-preview/` 对齐
- 静态资源返回 200
- 页面关键交互可用
- 错误态可见且不崩页

## 8.3 外部联调结论

如果 Jira 继续被 403 阻塞，则本轮验收结论应明确写为：

- 本地实现完成
- 外部 Jira 联调受阻
- 阻塞原因来自外部响应而非页面或服务代码

## 9. 实施边界

本设计是一个单轮可执行实现范围，不再拆成独立子项目。原因如下：

1. 7 个页面共享同一套壳层和样式体系
2. Jira、sync2pod、integrations 都要出现在统一 workspace 中
3. 如果分拆实现，会重复返工壳层、导航、rail 和状态模型

因此实施顺序应当是：

1. 共享壳层与全局样式
2. Jira 页面迁移与重构
3. sync2pod 真实后端与页面
4. integrations 真实后端与页面
5. workspace 聚合页与最终联调

## 10. 成功标准

当以下条件同时满足时，本轮任务才算完成：

1. 7 个目标预览页均已迁移为 Django 正式页面
2. 页面结构和视觉层级与预览稿一致
3. Jira 四页可使用现有本地缓存与同步能力
4. sync2pod 页面已接真实配置和运行能力
5. integrations 页面已接真实目录和契约聚合能力
6. 自动化测试通过
7. 本地 UI 可启动并逐页验证
8. 外部 Jira 如仍阻塞，已在页面与验收说明中明确标注
