"""
sync2pod 告警通知 — 任务意外停止时发送邮件
"""

import threading
from datetime import datetime

from loguru import logger


def send_stop_alert(task) -> None:
    """在后台线程中发送告警邮件，不阻塞请求。"""
    threading.Thread(target=_send, args=(task,), daemon=True).start()


def _send(task) -> None:
    try:
        from .models import Sync2PodConfig
        config = Sync2PodConfig.get()
    except Exception as e:
        logger.warning(f"[alert] 读取配置失败: {e}")
        return

    if not config.alert_email or not config.smtp_host:
        logger.debug("[alert] 未配置告警邮箱或 SMTP，跳过发送")
        return

    subject = f'[Sync2Pod] 任务 "{task.name}" 意外停止'
    body = _build_body(task)

    try:
        from django.core.mail import get_connection, EmailMessage
        conn = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_user,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
            fail_silently=False,
        )
        from_email = config.smtp_user or f'sync2pod@{config.smtp_host}'
        msg = EmailMessage(subject, body, from_email, [config.alert_email], connection=conn)
        msg.send()
        logger.info(f"[alert] 告警邮件已发送 → {config.alert_email}（任务：{task.name}）")
    except Exception as e:
        logger.error(f"[alert] 邮件发送失败: {e}")


def _build_body(task) -> str:
    cluster_line = f"集群：      {task.cluster}\n" if task.cluster else ""
    container_line = f"容器：      {task.container}\n" if task.container else ""
    label_line = f"Pod 标签：  {task.pod_label}\n" if task.pod_label else ""
    pod_line = f"Pod 名称：  {task.pod}\n" if task.pod else ""
    tess_line = "kubectl：   tess kubectl\n" if task.is_tess else ""

    return f"""\
Sync2Pod 监控告警

任务「{task.name}」已意外停止（非主动操作），请检查。

── 任务信息 ────────────────────────────────
任务名称：  {task.name}
本地目录：  {task.source_dir}
{cluster_line}命名空间：  {task.namespace}
{label_line}{pod_line}Pod 路径：  {task.pod_dir}
{container_line}{tess_line}轮询间隔：  {task.interval}s
停止时间：  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
─────────────────────────────────────────────

请登录 Sync2Pod 控制台检查日志并重新启动任务。
"""
