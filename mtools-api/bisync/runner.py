#!/usr/bin/env python3
"""
bisync runner — CLI 入口（也是 Django subprocess 的启动点）
核心逻辑见 engine.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bisync.engine import (
    DEFAULT_DEBOUNCE,
    DEFAULT_POLL_INTERVAL,
    do_initial_sync,
    do_watch_sync,
    find_unison,
    get_profile_name,
    get_state_path,
    load_state,
    save_state,
    setup_logging,
    setup_signal_handlers,
)
from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bisync",
        description="本地双向文件同步（基于 Unison）",
        epilog="""
示例:
  runner.py ~/scripts ~/project/scripts
  runner.py ~/scripts ~/project/scripts --name my-sync
  runner.py ~/scripts ~/project/scripts --reset   # 重新初始化
        """,
    )
    parser.add_argument("source_dir", help="源目录（必须已存在）")
    parser.add_argument("target_dir", help="目标目录（初始化时自动重建）")
    parser.add_argument("--name", default=None, metavar="NAME",
                        help="任务名称，用于状态文件目录（默认由路径自动生成）")
    parser.add_argument("--reset", action="store_true",
                        help="强制重新初始化：删除 target_dir，重新 cp -r")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL,
                        metavar="SEC",
                        help=f"轮询间隔（秒），fswatch 不可用时使用（默认: {DEFAULT_POLL_INTERVAL}）")
    parser.add_argument("--debounce", type=float, default=DEFAULT_DEBOUNCE,
                        metavar="SEC",
                        help=f"变更防抖延迟（秒），默认: {DEFAULT_DEBOUNCE}")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="PATTERN",
                        help="排除 glob 模式（可多次使用），如 --exclude __pycache__ --exclude '*.pyc'")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)
    setup_signal_handlers()

    source_dir = Path(args.source_dir).expanduser().resolve()
    target_dir = Path(args.target_dir).expanduser().resolve()

    if not source_dir.is_dir():
        logger.error(f"❌ source_dir 不存在或不是目录: {source_dir}")
        sys.exit(1)

    unison = find_unison()
    logger.info(f"🔧 Unison: {unison}")
    logger.info(f"📂 source: {source_dir}")
    logger.info(f"📂 target: {target_dir}")

    profile = get_profile_name(source_dir, target_dir, args.name)
    state_path = get_state_path(profile)
    state = load_state(state_path)

    if args.reset:
        logger.info("🔄 --reset：清除状态，重新初始化")
        state = {}

    # target_dir 不存在时无论 state 如何都重新初始化（相当于重新建立链接）
    need_init = not state.get("initialized", False) or not target_dir.is_dir()

    if need_init:
        if not state.get("initialized", False):
            logger.info("🆕 首次运行，执行初始化")
        else:
            logger.info("🔗 target_dir 不存在（链接已断开），重新初始化")
        do_initial_sync(source_dir, target_dir)
        state.update({
            "initialized": True,
            "source_dir": str(source_dir),
            "target_dir": str(target_dir),
        })
        save_state(state_path, state)
    else:
        logger.info("ℹ️  已初始化，直接进入监控模式（--reset 可重新初始化）")

    do_watch_sync(unison, source_dir, target_dir,
                  interval=args.interval,
                  debounce_seconds=args.debounce,
                  ignore_patterns=args.exclude or [])


if __name__ == "__main__":
    main()
