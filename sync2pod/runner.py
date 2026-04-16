#!/usr/bin/env python3
"""
sync2pod runner — CLI 入口（也是 Django subprocess 的启动点）
核心逻辑见 engine.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync2pod.engine import (
    DEFAULT_POLL_INTERVAL,
    build_kubectl_cmd,
    do_initial_sync,
    do_watch_sync,
    setup_logging,
    setup_signal_handlers,
)
from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync2pod",
        description="本地目录单向同步到 Kubernetes Pod（基于 kubectl cp）",
        epilog="""
示例:
  runner.py ~/src my-pod /app/src
  runner.py ~/src "" /app/src --pod-label app=myapi --namespace dev
  runner.py ~/src "" /app/src --pod-label app=myapi --cluster prod --tess
        """,
    )
    parser.add_argument("source_dir", help="本地源目录（必须已存在）")
    parser.add_argument("pod",        help="Kubernetes Pod 名称（与 --pod-label 二选一，留空则必须指定 --pod-label）")
    parser.add_argument("pod_dir",    help="Pod 内目标路径")
    parser.add_argument("--pod-label",  default="", metavar="SELECTOR",
                        help="标签选择器（优先级高于 pod，e.g. app=myapi,env=dev）")
    parser.add_argument("--namespace",  default="default", metavar="NS",
                        help="Kubernetes 命名空间（默认: default）")
    parser.add_argument("--cluster",    default="",        metavar="CLUSTER",
                        help="Kubernetes 集群名称（kubeconfig 中的 cluster name，留空使用当前上下文）")
    parser.add_argument("--container",  default="",        metavar="CONTAINER",
                        help="容器名称（多容器 Pod 时使用）")
    parser.add_argument("--tess",       action="store_true",
                        help="使用 tess kubectl 替代 kubectl（Tess 环境）")
    parser.add_argument("--name",       default=None,      metavar="NAME",
                        help="任务名称，仅用于日志标识")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--interval",   type=int, default=DEFAULT_POLL_INTERVAL,
                        metavar="SEC",
                        help=f"轮询间隔（秒），fswatch 不可用时使用（默认: {DEFAULT_POLL_INTERVAL}）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)
    setup_signal_handlers()

    pod_name  = args.pod or ""
    pod_label = args.pod_label or ""

    if not pod_name and not pod_label:
        logger.error("❌ 必须指定 pod 名称或 --pod-label")
        sys.exit(1)

    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        logger.error(f"❌ source_dir 不存在或不是目录: {source_dir}")
        sys.exit(1)

    kubectl_cmd = build_kubectl_cmd(is_tess=args.tess)
    logger.info(f"📂 source:     {source_dir}")
    if pod_label:
        logger.info(f"🏷  pod-label:  {pod_label}")
    else:
        logger.info(f"☸️  pod:        {pod_name}")
    logger.info(f"📁 pod_dir:    {args.pod_dir}")
    logger.info(f"🌐 namespace:  {args.namespace}")
    if args.cluster:
        logger.info(f"🌐 cluster:    {args.cluster}")
    if args.container:
        logger.info(f"📦 container:  {args.container}")
    if args.tess:
        logger.info("🔑 mode:       tess kubectl")

    ok = do_initial_sync(
        kubectl_cmd, source_dir,
        pod_name, pod_label, args.pod_dir,
        args.namespace, args.container, args.cluster,
    )
    if not ok:
        logger.error("❌ 初始化失败，退出")
        sys.exit(1)

    do_watch_sync(
        kubectl_cmd, source_dir,
        pod_name, pod_label, args.pod_dir,
        args.namespace, args.container, args.cluster,
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
