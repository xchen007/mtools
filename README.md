# MTools

前后端分离工具集，包含 **Bisync**（本地双向文件同步）和 **Sync2Pod**（本地→Kubernetes Pod 同步）。

## 项目结构

```
mtools/
├── mtools-api/   # 后端（Django + DRF + Django Channels，需 Python 3.12+）
└── mtools-web/   # 前端（Vue 3 + Element Plus）
```

> 后端 `.venv` 使用 Python 3.13（Homebrew），Django 5.2 LTS，支持 Python 3.10+。

```
```

## 启动

前后端是**两个独立服务**，需同时启动。

### 后端（开发模式，代码改变自动重启）

```bash
cd ~/workspace/mtools/mtools-api
.venv/bin/python manage.py runserver 8009
```

> ⚠️ 直接用 `.venv/bin/python` 而非 `python` / `python3`，避免系统 alias 指向错误版本。

### 后端（生产模式）

```bash
cd ~/workspace/mtools/mtools-api
.venv/bin/python -m daphne -p 8009 config.asgi:application
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

```bash
# 后端（需 Python 3.10+，使用 venv 内的 pip）
cd ~/workspace/mtools/mtools-api
.venv/bin/pip install -r requirements.txt

# 前端
cd ~/workspace/mtools/mtools-web && npm install
```

- Bisync 需要 [unison](https://github.com/bcpierce00/unison)：`brew install unison`
- 实时监控（可选，更低延迟）：`brew install fswatch`
