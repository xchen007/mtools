# MTools

本地工具可视化管理平台（Django）

## 启动服务

```bash
cd /Users/xchen17/workspace/github/mtools
make run        # 启动开发服务器（端口 8008）
```

访问 http://127.0.0.1:8008/

## 其他命令

```bash
make migrate    # 执行数据库迁移
make shell      # 进入 Django shell
```

## 功能

- **Bisync** — 本地双向文件同步任务管理（基于 [bisync.py](../myscript/bisync/bisync.py)）
  - 新建 / 启动 / 停止 / 删除任务
  - 重置同步状态（重新触发首次 source→target 覆盖同步）
  - 实时日志查看（2 秒自动刷新）

- **Sync2Pod** — 本地目录单向同步到 Kubernetes Pod（基于 `kubectl cp`）
  - 新建 / 启动 / 停止 / 删除任务
  - 支持指定命名空间、Pod 名称、容器名称（多容器 Pod）、Pod 内目标路径
  - 优先使用 fswatch 实时监控，自动降级为轮询模式
  - 实时日志查看（2 秒自动刷新）
