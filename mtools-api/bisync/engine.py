"""
bisync engine — 本地双向文件同步核心逻辑（基于 Unison）

初始化：rm -rf target_dir → cp -r source_dir/ target_dir/（完全一致）
监控：  双向同步子文件/子目录；根目录消失时跳过同步等待用户重置
"""

import hashlib
import json
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

UNISON_BIN = os.environ.get("UNISON_BIN", "unison")
STATE_DIR = Path.home() / ".bisync"
DEFAULT_POLL_INTERVAL = 3
DEFAULT_DEBOUNCE = 1.0

# 临时文件后缀/前缀（与 sync2pod 保持一致）
_TEMP_SUFFIXES = ("~", ".swp", ".swo", ".swn", ".tmp", ".bak", ".temp")
_TEMP_PREFIXES = (".#", "~")


def _is_temp_file(path: str) -> bool:
    name = os.path.basename(path)
    return (
        any(name.endswith(s) for s in _TEMP_SUFFIXES)
        or any(name.startswith(p) for p in _TEMP_PREFIXES)
        or ".tmp." in name
        or name.endswith("#")
    )


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


# ========== 状态文件 ==========

def get_profile_name(source_dir: Path, target_dir: Path, name: str | None) -> str:
    if name:
        return name
    combined = f"{source_dir.resolve()}::{target_dir.resolve()}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]


def get_state_path(profile: str) -> Path:
    return STATE_DIR / profile / "state.json"


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state_path: Path, data: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ========== Unison 工具 ==========

def find_unison() -> str:
    if UNISON_BIN != "unison":
        if Path(UNISON_BIN).is_file():
            return UNISON_BIN
        logger.error(f"❌ UNISON_BIN 指向的路径不存在: {UNISON_BIN}")
        sys.exit(1)

    resolved = shutil.which("unison")
    if resolved:
        return resolved

    for candidate in [
        Path.home() / ".opam/default/bin/unison",
        Path("/usr/local/bin/unison"),
        Path("/opt/homebrew/bin/unison"),
    ]:
        if candidate.is_file():
            return str(candidate)

    logger.error("❌ 未找到 unison，请先安装: brew install unison 或 opam install unison")
    sys.exit(1)


def run_unison(
    unison: str,
    source_dir: Path,
    target_dir: Path,
    extra_args: list,
    ignore_patterns: list | None = None,
    capture_stderr: bool = False,
) -> tuple[int, str]:
    """执行 unison，返回 (退出码, stderr)。退出码: 0=成功 1=部分跳过 2=致命错误"""
    ignore_args = []
    for pat in (ignore_patterns or []):
        ignore_args += ["-ignore", f"Name {pat}"]

    cmd = [
        unison,
        str(source_dir), str(target_dir),
        "-auto", "-batch", "-ui", "text",
    ] + ignore_args + extra_args

    logger.debug(f"执行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stderr=subprocess.PIPE if capture_stderr else None,
            text=True,
        )
        return result.returncode, result.stderr or ""
    except FileNotFoundError:
        logger.error(f"❌ 找不到 unison 可执行文件: {unison}")
        sys.exit(1)


# ========== 初始化 ==========

def do_initial_sync(source_dir: Path, target_dir: Path) -> bool:
    """初始化：删除 target_dir，完整复制 source_dir → target_dir。
    保证两侧内容完全一致，作为 unison 双向同步的干净基准。
    """
    logger.info(f"🚀 初始化同步: {source_dir} → {target_dir}")

    if target_dir.exists():
        logger.info(f"🗑  删除已有 target_dir: {target_dir}")
        shutil.rmtree(target_dir)

    logger.info("📋 复制 source_dir → target_dir ...")
    shutil.copytree(str(source_dir), str(target_dir))
    logger.info("✅ 初始化完成，两侧内容完全一致")
    return True


# ========== 根目录保护 ==========

def _source_ok(source_dir: Path) -> bool:
    if not source_dir.is_dir():
        logger.error(f"🚫 source 根目录不存在，跳过同步: {source_dir}")
        return False
    return True


def _target_ok(target_dir: Path) -> bool:
    """target 根目录存在时返回 True；消失时记录日志并退出进程。"""
    if not target_dir.is_dir():
        logger.warning(
            f"⏹  target 根目录已被删除，停止同步任务: {target_dir}"
        )
        sys.exit(0)
    return True


def _roots_ok(source_dir: Path, target_dir: Path) -> bool:
    """同步前校验两侧根目录。source 消失→跳过；target 消失→退出进程。"""
    if not _source_ok(source_dir):
        return False
    _target_ok(target_dir)   # 不存在时内部 sys.exit
    return True


# ========== 监控 ==========

def do_watch_sync(
    unison: str,
    source_dir: Path,
    target_dir: Path,
    interval: int = DEFAULT_POLL_INTERVAL,
    debounce_seconds: float = DEFAULT_DEBOUNCE,
    ignore_patterns: list | None = None,
) -> None:
    """持续双向监控同步（阻塞直到退出信号）。
    优先使用 fswatch（实时），否则降级为自管理轮询循环。
    """
    logger.info(f"👀 启动双向监控: {source_dir} ↔ {target_dir}（Ctrl+C 退出）")
    logger.info("🔒 根目录保护：任一根目录消失时跳过同步，不会误删对端文件")
    if ignore_patterns:
        logger.info(f"🚫 排除模式: {', '.join(ignore_patterns)}")

    fswatch_bin = shutil.which("fswatch")
    if fswatch_bin:
        logger.info("✅ 使用 fswatch 实时监控（FSEvents）")
        _watch_with_fswatch(unison, fswatch_bin, source_dir, target_dir,
                            debounce_seconds=debounce_seconds,
                            ignore_patterns=ignore_patterns)
        return

    logger.warning(f"⚠️  fswatch 未找到，降级到轮询模式（每 {interval} 秒）")
    logger.info("提示: brew install fswatch 可获得实时监控")
    _watch_poll(unison, source_dir, target_dir, interval,
                ignore_patterns=ignore_patterns)


def _watch_poll(
    unison: str,
    source_dir: Path,
    target_dir: Path,
    interval: int,
    ignore_patterns: list | None = None,
) -> None:
    while True:
        time.sleep(interval)
        if not _roots_ok(source_dir, target_dir):
            continue
        logger.debug("🔄 轮询触发同步")
        rc, _ = run_unison(unison, source_dir, target_dir, extra_args=[],
                           ignore_patterns=ignore_patterns)
        if rc == 2:
            logger.error("❌ 同步失败")


def _watch_with_fswatch(
    unison: str,
    fswatch_bin: str,
    source_dir: Path,
    target_dir: Path,
    debounce_seconds: float = DEFAULT_DEBOUNCE,
    ignore_patterns: list | None = None,
) -> None:
    sync_lock = threading.Lock()
    pending = threading.Event()
    stop_event = threading.Event()

    def sync_worker() -> None:
        while not stop_event.is_set():
            pending.wait(timeout=1.0)
            if not pending.is_set():
                continue
            pending.clear()
            time.sleep(debounce_seconds)
            if pending.is_set():
                continue
            with sync_lock:
                if not source_dir.is_dir():
                    logger.error(f"🚫 source 根目录不存在，跳过同步: {source_dir}")
                    continue
                if not target_dir.is_dir():
                    logger.warning(
                        f"⏹  target 根目录已被删除，停止同步任务: {target_dir}"
                    )
                    stop_event.set()
                    os._exit(0)   # 从子线程退出整个进程
                logger.debug("🔄 检测到变更，触发同步")
                rc, _ = run_unison(unison, source_dir, target_dir, extra_args=[],
                                   ignore_patterns=ignore_patterns)
                if rc == 2:
                    logger.error("❌ 同步失败")

    threading.Thread(target=sync_worker, daemon=True).start()

    cmd = [
        fswatch_bin, "--recursive",
        "--event=Created", "--event=Updated", "--event=Removed",
        "--event=Renamed", "--event=MovedFrom", "--event=MovedTo",
        "--latency=0.5",
        str(source_dir), str(target_dir),
    ]
    logger.debug(f"fswatch: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    try:
        for line in proc.stdout:
            changed = line.strip()
            if changed and not _is_temp_file(changed):
                logger.debug(f"变更: {changed}")
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
