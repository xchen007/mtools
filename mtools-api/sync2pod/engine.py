"""
sync2pod engine — 本地目录单向同步到 Kubernetes Pod（基于 kubectl cp）

Pod 解析策略（K8s）：
  - pod_label 优先：通过标签选择器查找唯一 Running Pod（适应 Pod 频繁重建场景）
  - pod_name  兜底：直接使用指定名称
  - 每次同步前重新解析，保证使用最新 Pod 名称

kubectl 命令：
  - 普通模式: kubectl ...
  - Tess 模式: tess kubectl ...（通过 --tess 标志启用）
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from loguru import logger


# ========== 常量 ==========

KUBECTL_BIN = os.environ.get("KUBECTL_BIN", "kubectl")
DEFAULT_POLL_INTERVAL = 3
FSWATCH_DEBOUNCE = 1.0


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


def build_kubectl_cmd(is_tess: bool = False) -> list[str]:
    """返回 kubectl 命令前缀列表。
    - 普通模式: ['/path/to/kubectl']
    - Tess 模式: ['tess', 'kubectl']
    """
    if is_tess:
        tess_bin = shutil.which("tess")
        if not tess_bin:
            logger.error("❌ 未找到 tess，请先安装 tess CLI")
            sys.exit(1)
        logger.info(f"🔧 tess kubectl: {tess_bin} kubectl")
        return [tess_bin, "kubectl"]
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


def run_kubectl_cp(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod: str,
    pod_dir: str,
    namespace: str,
    container: str = "",
    cluster: str = "",
) -> tuple[int, str]:
    """执行 kubectl cp source_dir/. pod:pod_dir，返回 (退出码, stderr)。"""
    pod_target = f"{pod}:{pod_dir}"
    cmd = kubectl_cmd + ["cp", f"{source_dir}/.", pod_target, "-n", namespace]
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
) -> None:
    """持续监控本地变更并同步到 Pod（阻塞直到退出信号）。
    优先使用 fswatch（实时），否则降级为轮询。
    每次同步前重新解析 Pod 名称（label 模式下应对 Pod 重建）。
    """
    id_str = f"[{pod_label}]" if pod_label else pod_name
    cluster_info = f" [{cluster}]" if cluster else ""
    logger.info(f"👀 启动监控: {source_dir} → {namespace}/{id_str}:{pod_dir}{cluster_info}（Ctrl+C 退出）")

    fswatch_bin = shutil.which("fswatch")
    if fswatch_bin:
        logger.info("✅ 使用 fswatch 实时监控（FSEvents）")
        _watch_with_fswatch(
            kubectl_cmd, fswatch_bin, source_dir,
            pod_name, pod_label, pod_dir, namespace, container, cluster,
        )
        return

    logger.warning(f"⚠️  fswatch 未找到，降级到轮询模式（每 {interval} 秒）")
    logger.info("提示: brew install fswatch 可获得实时监控")
    _watch_poll(kubectl_cmd, source_dir, pod_name, pod_label, pod_dir, namespace, container, cluster, interval)


def _do_sync(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod_name: str,
    pod_label: str,
    pod_dir: str,
    namespace: str,
    container: str,
    cluster: str,
) -> None:
    if not source_dir.is_dir():
        logger.error(f"🚫 source 目录不存在，跳过同步: {source_dir}")
        return

    resolved, err = resolve_pod_name(kubectl_cmd, pod_name, pod_label, namespace, cluster)
    if err:
        logger.warning(f"⏸  跳过同步: {err}")
        return

    rc, stderr = run_kubectl_cp(kubectl_cmd, source_dir, resolved, pod_dir, namespace, container, cluster)
    if rc != 0:
        logger.error(f"❌ 同步失败（exit {rc}）: {stderr.strip()}")
    else:
        logger.debug(f"✅ 同步完成 → {resolved}")


def _watch_poll(
    kubectl_cmd: list[str],
    source_dir: Path,
    pod_name: str,
    pod_label: str,
    pod_dir: str,
    namespace: str,
    container: str,
    cluster: str,
    interval: int,
) -> None:
    while True:
        time.sleep(interval)
        logger.debug("🔄 轮询触发同步")
        _do_sync(kubectl_cmd, source_dir, pod_name, pod_label, pod_dir, namespace, container, cluster)


def _watch_with_fswatch(
    kubectl_cmd: list[str],
    fswatch_bin: str,
    source_dir: Path,
    pod_name: str,
    pod_label: str,
    pod_dir: str,
    namespace: str,
    container: str,
    cluster: str,
) -> None:
    pending = threading.Event()
    stop_event = threading.Event()

    def sync_worker() -> None:
        while not stop_event.is_set():
            pending.wait(timeout=1.0)
            if not pending.is_set():
                continue
            pending.clear()
            time.sleep(FSWATCH_DEBOUNCE)
            if pending.is_set():
                continue
            logger.debug("🔄 检测到变更，触发同步")
            _do_sync(kubectl_cmd, source_dir, pod_name, pod_label, pod_dir, namespace, container, cluster)

    threading.Thread(target=sync_worker, daemon=True).start()

    cmd = [
        fswatch_bin, "--recursive",
        "--event=Created", "--event=Updated", "--event=Removed",
        "--event=Renamed", "--event=MovedFrom", "--event=MovedTo",
        "--latency=0.5",
        str(source_dir),
    ]
    logger.debug(f"fswatch: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    try:
        for line in proc.stdout:
            if line.strip():
                logger.debug(f"变更: {line.strip()}")
                pending.set()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        proc.terminate()
        proc.wait()


# ========== 信号处理 ==========

def setup_signal_handlers() -> None:
    def _handler(sig, frame):
        logger.info("\n⏹  收到退出信号，停止同步")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
