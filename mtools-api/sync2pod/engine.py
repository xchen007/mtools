"""
sync2pod engine — 本地目录单向同步到 Kubernetes Pod（基于 kubectl cp）

Pod 解析策略（K8s）：
  - pod_label 优先：通过标签选择器查找唯一 Running Pod（适应 Pod 频繁重建场景）
  - pod_name  兜底：直接使用指定名称
  - 每次同步前重新解析，保证使用最新 Pod 名称

kubectl 命令：
  - 普通模式: kubectl ...
  - Tess 模式: tess kubectl ...（通过 --tess 标志启用）

文件监控机制：
  - 使用 watchdog 库实时监控文件系统变更（替代 fswatch）
  - 自动排除 VCS 目录（.git, .svn 等）、临时文件（.swp, ~, .tmp 等）、隐藏文件
  - 防抖机制：连续变更会合并为单次同步（默认 1.0s）
  - 并发上传：使用线程池处理多文件同步

支持的文件变更检测：
  - 新建文件（touch, IDE 新建等）
  - 文件修改（IDE 保存、AI agent 修改等）
  - 文件移动/重命名
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


# ========== 常量 ==========

KUBECTL_BIN = os.environ.get("KUBECTL_BIN", "kubectl")
DEFAULT_POLL_INTERVAL = 3
FSWATCH_DEBOUNCE = 1.0
BATCH_UPLOAD_THRESHOLD = 10  # When N+ files change, use batch upload instead of individual uploads
BATCH_COLLECT_WINDOW = 2.0   # Collect files for N seconds before batch upload

# Directories and files to exclude from sync (VCS and common ignored patterns)
SYNC_EXCLUDE_PATTERNS = {
    ".git", ".svn", ".hg", ".bzr",  # Version control
    "__pycache__", "*.pyc", ".pytest_cache",  # Python
    "node_modules", ".npm",  # Node.js
    ".idea", ".vscode", ".DS_Store",  # IDEs and OS
}

# Temporary file patterns (editor auto-save, swap files, etc.)
TEMP_FILE_SUFFIXES = ("~", ".swp", ".swo", ".swn", ".tmp", ".bak", ".temp", "#")
TEMP_FILE_PREFIXES = (".#", "~")
TEMP_FILE_PATTERNS = (".tmp.",)


# ========== 文件过滤工具 ==========

def is_temp_file(name: str) -> bool:
    """Check if a file is a temporary file (editor swap, auto-save, etc.)."""
    return (
        any(name.endswith(s) for s in TEMP_FILE_SUFFIXES)
        or any(name.startswith(p) for p in TEMP_FILE_PREFIXES)
        or any(pattern in name for pattern in TEMP_FILE_PATTERNS)
    )


def is_hidden(path: str) -> bool:
    """Check if any part of the path starts with a dot (hidden file/directory)."""
    return any(part.startswith(".") for part in Path(path).parts)


def should_exclude_path(file_path: Path, source_dir: Path) -> bool:
    """Check if a file path should be excluded from sync."""
    # Check if it's a hidden file/directory
    if is_hidden(str(file_path)):
        return True

    # Check if filename is a temporary file
    if is_temp_file(file_path.name):
        return True

    # Check against exclude patterns
    try:
        rel_path = file_path.relative_to(source_dir)
        rel_str = str(rel_path)
        for pattern in SYNC_EXCLUDE_PATTERNS:
            # Skip wildcard patterns for now
            if '*' in pattern:
                continue
            # Check if path starts with pattern or contains it as a directory
            if rel_str == pattern or rel_str.startswith(pattern + os.sep):
                return True
    except ValueError:
        # Path is not relative to source_dir
        return True

    return False


# ========== 同步时间戳更新 ==========

_last_db_update_time = {}  # {task_name: timestamp}
_db_update_lock = threading.Lock()
DB_UPDATE_THROTTLE = 5.0  # Only update DB every N seconds


def update_last_sync_time(task_name: str, force: bool = False) -> None:
    """Update last_sync_at timestamp in database for the task.

    Optimized: Throttles DB updates to max once per DB_UPDATE_THROTTLE seconds.
    """
    if not task_name:
        return

    try:
        now = time.time()

        # Throttle: skip if updated recently (unless forced)
        with _db_update_lock:
            last_update = _last_db_update_time.get(task_name, 0)
            if not force and (now - last_update) < DB_UPDATE_THROTTLE:
                logger.debug(f"跳过数据库更新（节流）: {task_name}")
                return
            _last_db_update_time[task_name] = now

        # Import Django models inside the function to avoid circular imports
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        django.setup()

        from sync2pod.models import Sync2PodTask
        from django.utils import timezone

        task = Sync2PodTask.objects.filter(name=task_name).first()
        if task:
            task.last_sync_at = timezone.now()
            task.save(update_fields=['last_sync_at'])
            logger.debug(f"更新同步时间戳: {task_name}")
    except Exception as e:
        logger.warning(f"更新同步时间戳失败: {e}")


# ========== 日志 ==========

def setup_logging(verbose: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )


# ========== kubectl 工具 ==========

def find_kubectl() -> str:
    if KUBECTL_BIN != "kubectl":
        if Path(KUBECTL_BIN).is_file():
            return KUBECTL_BIN
        logger.error(f"❌ KUBECTL_BIN 指向的路径不存在: {KUBECTL_BIN}")
        sys.exit(1)

    resolved = shutil.which("kubectl")
    if resolved:
        return resolved

    for candidate in [
        Path.home() / ".local/bin/kubectl",
        Path("/usr/local/bin/kubectl"),
        Path("/opt/homebrew/bin/kubectl"),
    ]:
        if candidate.is_file():
            return str(candidate)

    logger.error("❌ 未找到 kubectl，请先安装或通过 KUBECTL_BIN 环境变量指定路径")
    sys.exit(1)


def build_kubectl_cmd(is_tess: bool = False, custom_cmd: str = "") -> list[str]:
    """返回 kubectl 命令前缀列表。
    - 自定义命令模式: custom_cmd 指定的命令（如 'tess kubectl'）
    - Tess 模式: ['tess', 'kubectl']（向后兼容）
    - 普通模式: ['/path/to/kubectl']

    优先级: custom_cmd > is_tess > 默认 kubectl
    """
    # 1. 优先使用自定义命令
    if custom_cmd:
        cmd_parts = custom_cmd.strip().split()
        logger.info(f"🔧 自定义 kubectl: {custom_cmd}")
        return cmd_parts

    # 2. 向后兼容 is_tess 参数
    if is_tess:
        tess_bin = shutil.which("tess")
        if not tess_bin:
            logger.error("❌ 未找到 tess，请先安装 tess CLI")
            sys.exit(1)
        logger.info(f"🔧 tess kubectl: {tess_bin} kubectl")
        return [tess_bin, "kubectl"]

    # 3. 默认使用 kubectl
    kubectl = find_kubectl()
    logger.info(f"🔧 kubectl: {kubectl}")
    return [kubectl]



def resolve_pod_name(
    kubectl_cmd: list[str],
    pod_name: str,
    pod_label: str,
    namespace: str,
    cluster: str = "",
) -> tuple[str | None, str | None]:
    """解析实际 Pod 名称。pod_label 优先级高于 pod_name。

    Returns:
        (pod_name, None)  — 成功
        (None, error_msg) — 失败
    """
    if pod_label:
        cmd = kubectl_cmd + [
            "get", "pods",
            "-n", namespace,
            "-l", pod_label,
            "--field-selector=status.phase=Running",
            "-o", "jsonpath={.items[*].metadata.name}",
        ]
        if cluster:
            cmd += ["--cluster", cluster]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return None, f"kubectl get pods 失败: {result.stderr.strip()}"
            names = result.stdout.strip().split()
            if len(names) == 0:
                return None, (
                    f"未找到标签 '{pod_label}' 对应的 Running Pod"
                    f"（namespace: {namespace}）"
                )
            if len(names) > 1:
                return None, (
                    f"标签 '{pod_label}' 匹配到多个 Running Pod: {', '.join(names)}，"
                    f"请使用更精确的标签"
                )
            return names[0], None
        except Exception as e:
            return None, f"查询 Pod 失败: {e}"

    if not pod_name:
        return None, "pod_name 和 pod_label 不能同时为空"
    return pod_name, None


def run_kubectl_cp_single_file(
    kubectl_cmd: list[str],
    file_path: Path,
    source_dir: Path,
    pod: str,
    pod_dir: str,
    namespace: str,
    container: str = "",
    cluster: str = "",
    max_retries: int = 3,
) -> tuple[int, str]:
    """执行单个文件的 kubectl cp，返回 (退出码, stderr)。

    优化版本：直接上传单个文件，无需 rsync 和临时目录。
    自动重试机制：失败后指数退避重试。
    """
    try:
        # Calculate relative path and remote destination
        rel_path = file_path.relative_to(source_dir)
        remote_file_path = f"{pod_dir}/{rel_path}".replace("\\", "/")

        # Build kubectl cp command for single file
        cmd = kubectl_cmd + ["cp", str(file_path), f"{pod}:{remote_file_path}", "-n", namespace]
        if container:
            cmd += ["-c", container]
        if cluster:
            cmd += ["--cluster", cluster]

        # Retry with exponential backoff
        for attempt in range(max_retries):
            logger.debug(f"执行: {' '.join(cmd)}" + (f" (重试 {attempt + 1}/{max_retries})" if attempt > 0 else ""))
            result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, timeout=300)

            if result.returncode == 0:
                return 0, result.stderr or ""

            # Failed - retry with exponential backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"⚠️  上传失败，{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                # Final attempt failed
                return result.returncode, result.stderr or ""

    except subprocess.TimeoutExpired:
        return 1, "kubectl cp timeout (300s)"
    except FileNotFoundError:
        logger.error(f"❌ 找不到命令: {kubectl_cmd[0]}")
        sys.exit(1)
    except Exception as e:
        return 1, str(e)


def run_kubectl_cp(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod: str,
    pod_dir: str,
    namespace: str,
    container: str = "",
    cluster: str = "",
) -> tuple[int, str]:
    """执行 kubectl cp source_dir/. pod:pod_dir，返回 (退出码, stderr)。

    Uses a temporary directory to filter out excluded patterns before copying.
    用于初始化同步，会过滤排除的文件/目录。
    """
    # Create a temporary directory for filtered content
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "sync_content"
        temp_path.mkdir()

        # Build rsync exclude arguments
        exclude_args = []
        for pattern in SYNC_EXCLUDE_PATTERNS:
            exclude_args.extend(["--exclude", pattern])

        # Use rsync to copy with exclusions
        rsync_cmd = [
            "rsync", "-a", "--delete",  # archive mode with delete (mirror source)
            *exclude_args,
            f"{source_dir}/",  # source with trailing slash (copies contents)
            f"{temp_path}/",   # destination
        ]

        logger.debug(f"过滤文件: {' '.join(rsync_cmd)}")
        rsync_result = subprocess.run(rsync_cmd, capture_output=True, text=True)

        if rsync_result.returncode != 0:
            return rsync_result.returncode, f"rsync 过滤失败: {rsync_result.stderr}"

        # Log what files are being synced
        try:
            files_count = sum(1 for _ in temp_path.rglob('*') if _.is_file())
            logger.debug(f"准备同步 {files_count} 个文件")
        except Exception:
            pass

        # Now use kubectl cp with the filtered content
        pod_target = f"{pod}:{pod_dir}"
        cmd = kubectl_cmd + ["cp", f"{temp_path}/.", pod_target, "-n", namespace]
        if container:
            cmd += ["-c", container]
        if cluster:
            cmd += ["--cluster", cluster]

        logger.debug(f"执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
            return result.returncode, result.stderr or ""
        except FileNotFoundError:
            logger.error(f"❌ 找不到命令: {cmd[0]}")
            sys.exit(1)


# ========== 初始化 ==========

def do_initial_sync(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod_name: str,
    pod_label: str,
    pod_dir: str,
    namespace: str,
    container: str = "",
    cluster: str = "",
) -> bool:
    cluster_info = f" [{cluster}]" if cluster else ""
    id_str = f"[{pod_label}]" if pod_label else pod_name
    logger.info(f"🚀 初始化同步: {source_dir} → {namespace}/{id_str}:{pod_dir}{cluster_info}")

    if not source_dir.is_dir():
        logger.error(f"❌ source_dir 不存在或不是目录: {source_dir}")
        return False

    resolved, err = resolve_pod_name(kubectl_cmd, pod_name, pod_label, namespace, cluster)
    if err:
        logger.error(f"❌ {err}")
        return False
    logger.info(f"✅ 解析到 Pod: {resolved}")

    rc, stderr = run_kubectl_cp(kubectl_cmd, source_dir, resolved, pod_dir, namespace, container, cluster)
    if rc != 0:
        logger.error(f"❌ 初始化同步失败（exit {rc}）: {stderr.strip()}")
        return False

    logger.info("✅ 初始化完成")
    return True


# ========== 文件变更监听器 ==========

class FileChangeHandler(FileSystemEventHandler):
    """Watchdog event handler for file system changes."""

    def __init__(
        self,
        kubectl_cmd: list[str],
        source_dir: Path,
        pod_name: str,
        pod_label: str,
        pod_dir: str,
        namespace: str,
        container: str = "",
        cluster: str = "",
        debounce: float = FSWATCH_DEBOUNCE,
        task_name: str = "",
        max_workers: int = 5,
    ):
        self.kubectl_cmd = kubectl_cmd
        self.source_dir = source_dir
        self.pod_name = pod_name
        self.pod_label = pod_label
        self.pod_dir = pod_dir
        self.namespace = namespace
        self.container = container
        self.cluster = cluster
        self.debounce = debounce
        self.task_name = task_name
        self.max_workers = max(1, min(max_workers, 20))  # Clamp to 1-20

        self.processing_files: dict = {}
        self.debounce_timers: dict = {}
        self.pending_uploads: dict = {}
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # Batch upload tracking
        self.pending_batch_files: set = set()  # Files waiting for batch upload
        self.batch_timer: threading.Timer | None = None

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        if not should_exclude_path(file_path, self.source_dir):
            logger.debug(f"[监听] modified: {file_path}")
            self._schedule_sync(file_path)

    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        if not should_exclude_path(file_path, self.source_dir):
            logger.debug(f"[监听] created: {file_path}")
            self._schedule_sync(file_path)

    def on_moved(self, event):
        """Handle file move/rename events."""
        if event.is_directory:
            return
        dest_path = Path(event.dest_path)
        # Only sync if destination is within source_dir and not excluded
        if dest_path.is_relative_to(self.source_dir) and not should_exclude_path(dest_path, self.source_dir):
            logger.debug(f"[监听] moved: {event.src_path} -> {dest_path}")
            self._schedule_sync(dest_path)

    def _schedule_sync(self, file_path: Path) -> None:
        """Schedule a debounced sync for the given file.

        Uses batch upload when multiple files change simultaneously.
        """
        rel_path = file_path.relative_to(self.source_dir)

        # If already processing, mark as pending
        fut = self.processing_files.get(str(file_path))
        if fut and not fut.done():
            self.pending_uploads[str(file_path)] = True
            logger.debug(f"正在上传，打待上传标记: {rel_path}")
            return

        # Cancel existing individual debounce timer
        old_timer = self.debounce_timers.pop(str(file_path), None)
        if old_timer and old_timer.is_alive():
            old_timer.cancel()

        # Add to batch pending set
        self.pending_batch_files.add(str(file_path))
        logger.info(f"🔍 检测到文件变更: {rel_path} (批量待传: {len(self.pending_batch_files)})")

        # If batch threshold reached, trigger batch upload immediately
        if len(self.pending_batch_files) >= BATCH_UPLOAD_THRESHOLD:
            logger.info(f"📦 达到批量阈值({BATCH_UPLOAD_THRESHOLD})，触发批量上传")
            if self.batch_timer and self.batch_timer.is_alive():
                self.batch_timer.cancel()
            self._trigger_batch_upload()
        else:
            # Reset batch timer
            if self.batch_timer and self.batch_timer.is_alive():
                self.batch_timer.cancel()
            self.batch_timer = threading.Timer(BATCH_COLLECT_WINDOW, self._trigger_batch_upload)
            self.batch_timer.start()

    def _trigger_batch_upload(self) -> None:
        """Trigger batch upload for all pending files."""
        if not self.pending_batch_files:
            return

        files_to_upload = list(self.pending_batch_files)
        self.pending_batch_files.clear()
        self.batch_timer = None

        # Decide: batch upload or individual uploads
        if len(files_to_upload) >= BATCH_UPLOAD_THRESHOLD:
            logger.info(f"📦 批量上传 {len(files_to_upload)} 个文件")
            self.executor.submit(self._batch_sync_all)
        else:
            logger.info(f"⚡ 单文件上传模式 ({len(files_to_upload)} 个文件)")
            for file_path_str in files_to_upload:
                file_path = Path(file_path_str)
                self.processing_files[file_path_str] = self.executor.submit(
                    self._sync_file, file_path
                )

    def _batch_sync_all(self) -> None:
        """Perform batch sync of entire source directory using rsync."""
        try:
            # Re-resolve pod name
            resolved, err = resolve_pod_name(
                self.kubectl_cmd, self.pod_name, self.pod_label,
                self.namespace, self.cluster
            )
            if err:
                logger.warning(f"⏸  跳过批量同步: {err}")
                return

            # Use full directory sync with rsync filtering
            logger.info("📦 执行批量同步（rsync模式）")
            rc, stderr = run_kubectl_cp(
                self.kubectl_cmd, self.source_dir, resolved,
                self.pod_dir, self.namespace, self.container, self.cluster
            )

            if rc != 0:
                logger.error(f"❌ 批量同步失败（exit {rc}）: {stderr.strip()}")
            else:
                logger.success(f"✅ 批量同步成功")
                # Update last sync timestamp
                if self.task_name:
                    update_last_sync_time(self.task_name)

        except Exception as e:
            logger.error(f"❌ 批量同步异常: {e}")

    def _debounced_sync(self, file_path: Path) -> None:
        """Execute sync after debounce period (legacy - not used in batch mode)."""
        self.debounce_timers.pop(str(file_path), None)

        # Check if already processing
        fut = self.processing_files.get(str(file_path))
        if fut and not fut.done():
            self.pending_uploads[str(file_path)] = True
            return

        # Submit sync task to executor
        self.processing_files[str(file_path)] = self.executor.submit(
            self._sync_file, file_path
        )

    def _sync_file(self, file_path: Path) -> None:
        """Sync a single file to the pod."""
        try:
            if not file_path.exists():
                logger.debug(f"文件已删除，跳过同步: {file_path}")
                return

            # Re-resolve pod name (in case pod was recreated)
            resolved, err = resolve_pod_name(
                self.kubectl_cmd, self.pod_name, self.pod_label,
                self.namespace, self.cluster
            )
            if err:
                logger.warning(f"⏸  跳过同步: {err}")
                return

            # Perform single file sync (optimized - no rsync overhead)
            rc, stderr = run_kubectl_cp_single_file(
                self.kubectl_cmd, file_path, self.source_dir, resolved,
                self.pod_dir, self.namespace, self.container, self.cluster
            )

            rel_path = file_path.relative_to(self.source_dir)
            if rc != 0:
                logger.error(f"❌ 同步失败: {rel_path} - {stderr.strip()}")
            else:
                logger.success(f"✅ 文件同步成功: {rel_path}")
                # Update last sync timestamp in database
                if self.task_name:
                    update_last_sync_time(self.task_name)

        except Exception as e:
            logger.error(f"❌ 同步异常: {file_path} - {e}")

        finally:
            # Clean up and check for pending uploads
            self.processing_files.pop(str(file_path), None)
            if self.pending_uploads.pop(str(file_path), False):
                rel_path = file_path.relative_to(self.source_dir)
                logger.info(f"🔄 检测到新变更，将在 {self.debounce}s 后重新上传: {rel_path}")
                timer = threading.Timer(self.debounce, self._debounced_sync, args=[file_path])
                self.debounce_timers[str(file_path)] = timer
                timer.start()

    def shutdown(self):
        """Shutdown the handler and cleanup resources."""
        # Cancel batch timer
        if self.batch_timer and self.batch_timer.is_alive():
            self.batch_timer.cancel()

        # Cancel all pending individual timers
        for timer in self.debounce_timers.values():
            if timer and timer.is_alive():
                timer.cancel()
        self.debounce_timers.clear()

        # Wait for in-flight uploads
        self.executor.shutdown(wait=True)


# ========== 监控 ==========

def do_watch_sync(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod_name: str,
    pod_label: str,
    pod_dir: str,
    namespace: str,
    container: str = "",
    cluster: str = "",
    interval: int = DEFAULT_POLL_INTERVAL,
    task_name: str = "",
    max_workers: int = 5,
) -> None:
    """持续监控本地变更并同步到 Pod（阻塞直到退出信号）。
    使用 watchdog 库进行实时文件监控。
    每次同步前重新解析 Pod 名称（label 模式下应对 Pod 重建）。
    """
    id_str = f"[{pod_label}]" if pod_label else pod_name
    cluster_info = f" [{cluster}]" if cluster else ""
    logger.info(f"👀 启动监控: {source_dir} → {namespace}/{id_str}:{pod_dir}{cluster_info}（Ctrl+C 退出）")
    logger.info(f"✅ 使用 watchdog 实时监控（防抖: {FSWATCH_DEBOUNCE}s, 并发: {max_workers}）")

    # Create event handler and observer
    handler = FileChangeHandler(
        kubectl_cmd, source_dir, pod_name, pod_label,
        pod_dir, namespace, container, cluster, FSWATCH_DEBOUNCE, task_name, max_workers
    )
    observer = Observer()
    observer.schedule(handler, path=str(source_dir), recursive=True)
    observer.start()

    logger.success(f"✅ 监听已启动: {source_dir}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n⏹  收到退出信号，停止监控...")
    finally:
        observer.stop()
        observer.join()
        handler.shutdown()
        logger.info("✅ 监控已停止")


# ========== 信号处理 ==========

def setup_signal_handlers() -> None:
    def _handler(sig, frame):
        logger.info("\n⏹  收到退出信号，停止同步")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
