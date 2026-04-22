# MTools

前后端分离工具集，包含 **Bisync**（本地双向文件同步）和 **Sync2Pod**（本地→Kubernetes Pod 同步）。

## 项目结构

```
mtools/
├── mtools-api/   # 后端（Django + DRF + Django Channels，需 Python 3.10+）
│   └── venv/     # Python 虚拟环境（或 .venv/）
└── mtools-web/   # 前端（Vue 3 + Element Plus）
    └── node_modules/
```

> 后端使用虚拟环境（`venv/` 或 `.venv/`），Django 5.2 LTS，支持 Python 3.10+。

```
```

## 启动

前后端是**两个独立服务**，需同时启动。

### 后端（开发模式，代码改变自动重启）

```bash
cd ~/workspace/mtools/mtools-api

# 使用虚拟环境的 Python（推荐）
venv/bin/python manage.py runserver 8009
# 或使用 .venv/bin/python（如果你的虚拟环境是 .venv/）

# 或先激活虚拟环境
source venv/bin/activate  # 或 source .venv/bin/activate
python manage.py runserver 8009
```

> ⚠️ 直接使用 `venv/bin/python` 或 `.venv/bin/python`，避免系统 Python 版本冲突和缺少依赖的问题。

### 后端（生产模式）

```bash
cd ~/workspace/mtools/mtools-api
venv/bin/python -m daphne -p 8009 config.asgi:application
# 或 .venv/bin/python -m daphne -p 8009 config.asgi:application
```

### 前端（Vite HMR，代码改变自动热更新）

```bash
cd ~/workspace/mtools/mtools-web
npm run dev
```

浏览器访问：http://localhost:5173

## 端口配置

若后端使用非默认端口（如 8009），在 `mtools-web/` 目录创建 `.env.local`：

```env
VITE_API_BASE_URL=http://localhost:8009
VITE_WS_BASE_URL=ws://localhost:8009
```

参考模板：`mtools-web/.env.example`

## 依赖安装

### 后端虚拟环境设置

⚠️ **重要**：后端依赖必须安装在虚拟环境中，避免与系统 Python 包冲突。

**首次设置**（如果还没有虚拟环境）：

```bash
cd ~/workspace/mtools/mtools-api

# 创建虚拟环境（二选一）
python -m venv venv        # 创建 venv/
# 或
python -m venv .venv       # 创建 .venv/（隐藏目录）

# 激活虚拟环境
source venv/bin/activate   # 如果使用 venv/
# 或
source .venv/bin/activate  # 如果使用 .venv/

# 安装依赖
pip install -r requirements.txt
```

**日常使用**（虚拟环境已存在）：

```bash
cd ~/workspace/mtools/mtools-api

# 方式 1: 激活虚拟环境后使用
source venv/bin/activate   # 或 source .venv/bin/activate
python manage.py runserver 8009

# 方式 2: 直接使用虚拟环境的 Python（无需激活）
venv/bin/python manage.py runserver 8009   # 或 .venv/bin/python
```

### 前端依赖

```bash
cd ~/workspace/mtools/mtools-web
npm install
```

### 额外工具

- Bisync 需要 [unison](https://github.com/bcpierce00/unison)：`brew install unison`
- 实时监控（可选，更低延迟）：`brew install fswatch`
