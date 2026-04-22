import os
import signal
from pathlib import Path

from django.db import models


class Sync2PodTask(models.Model):
    STATUS_STOPPED = 'stopped'
    STATUS_RUNNING = 'running'
    STATUS_ERROR   = 'error'
    STATUS_CHOICES = [
        (STATUS_STOPPED, '已停止'),
        (STATUS_RUNNING, '运行中'),
        (STATUS_ERROR,   '错误'),
    ]

    POD_TYPE_K8S    = 'k8s'
    POD_TYPE_DOCKER = 'docker'
    POD_TYPE_CHOICES = [
        (POD_TYPE_K8S,    'Kubernetes Pod'),
        (POD_TYPE_DOCKER, 'Docker 容器'),
    ]

    name      = models.CharField(max_length=100, unique=True, verbose_name='任务名称')
    pod_type  = models.CharField(max_length=20, choices=POD_TYPE_CHOICES,
                                 default=POD_TYPE_K8S, verbose_name='Pod 类型')
    source_dir = models.CharField(max_length=500, verbose_name='本地源目录')

    # ── Kubernetes 参数 ──────────────────────────────────────────────────────
    cluster   = models.CharField(max_length=200, blank=True, verbose_name='集群名称')
    namespace = models.CharField(max_length=100, default='default', verbose_name='命名空间')
    pod_label = models.CharField(max_length=500, blank=True, verbose_name='Pod 标签选择器',
                                 help_text='优先级高于 Pod 名称，e.g. app=myapp,env=dev')
    pod       = models.CharField(max_length=200, blank=True, verbose_name='Pod 名称',
                                 help_text='pod_label 为空时使用')
    container = models.CharField(max_length=100, blank=True, verbose_name='容器名称')
    pod_dir   = models.CharField(max_length=500, verbose_name='Pod 内目标路径')

    # ── 通用参数 ─────────────────────────────────────────────────────────────
    is_tess   = models.BooleanField(default=True, verbose_name='Tess 环境',
                                    help_text='启用后 kubectl 替换为 tess kubectl')
    interval  = models.IntegerField(default=3, verbose_name='轮询间隔(秒)')
    max_workers = models.IntegerField(default=5, verbose_name='并发上传数',
                                      help_text='同时上传文件的最大数量（1-20）')
    enable_alert = models.BooleanField(default=True, verbose_name='异常停止告警',
                                       help_text='非主动停止时发送邮件告警（需配置全局 SMTP）')
    status    = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                 default=STATUS_STOPPED, verbose_name='状态')
    pid       = models.IntegerField(null=True, blank=True, verbose_name='进程ID')
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name='最后同步时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True,     verbose_name='更新时间')

    class Meta:
        verbose_name = 'Sync2Pod 任务'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def log_file(self) -> Path:
        return Path.home() / '.sync2pod' / self.name / 'output.log'

    @property
    def pod_identity(self) -> str:
        """Human-readable pod identifier (label or name)."""
        if self.pod_label:
            return f"[{self.pod_label}]"
        return self.pod

    def is_process_running(self) -> bool:
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        try:
            import subprocess as _sp
            result = _sp.run(
                ['ps', '-p', str(self.pid), '-o', 'stat='],
                capture_output=True, text=True, timeout=2,
            )
            stat = result.stdout.strip()
            return bool(stat) and 'Z' not in stat
        except Exception:
            return True

    def sync_status(self) -> bool:
        if self.status == self.STATUS_RUNNING and not self.is_process_running():
            self.status = self.STATUS_STOPPED
            self.pid = None
            self.save(update_fields=['status', 'pid', 'updated_at'])
            if self.enable_alert:
                from .notifications import send_stop_alert
                send_stop_alert(self)
            return True
        return False

    def terminate(self) -> None:
        if self.pid:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        self.status = self.STATUS_STOPPED
        self.pid = None
        self.save(update_fields=['status', 'pid', 'updated_at'])


class Sync2PodConfig(models.Model):
    """全局单例配置。通过 Sync2PodConfig.get() 获取唯一实例。"""

    is_tess = models.BooleanField(
        default=True,
        verbose_name='Tess 环境（全局默认）',
        help_text='启用后，新建任务默认勾选 tess kubectl；已有任务不受影响',
    )
    show_list_log = models.BooleanField(
        default=True,
        verbose_name='列表页显示日志',
        help_text='启用后，任务列表操作栏显示日志按钮，可展开内联日志面板',
    )

    # ── 自定义命令配置 ─────────────────────────────────────────────────────
    custom_kubectl_cmd = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='自定义 kubectl 命令',
        help_text='自定义 kubectl 命令（如 "tess kubectl"），留空使用默认 kubectl'
    )
    custom_docker_cmd = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='自定义 docker 命令',
        help_text='自定义 docker 命令，留空使用默认 docker（Docker 功能暂未实现）'
    )

    # ── 邮件告警 SMTP 配置 ─────────────────────────────────────────────────
    alert_email   = models.CharField(max_length=200, blank=True, verbose_name='告警收件邮箱',
                                     help_text='为空则不发送告警邮件')
    smtp_host     = models.CharField(max_length=200, blank=True, verbose_name='SMTP 主机',
                                     help_text='e.g. smtp.gmail.com')
    smtp_port     = models.IntegerField(default=587, verbose_name='SMTP 端口')
    smtp_user     = models.CharField(max_length=200, blank=True, verbose_name='SMTP 用户名')
    smtp_password = models.CharField(max_length=500, blank=True, verbose_name='SMTP 密码')
    smtp_use_tls  = models.BooleanField(default=True, verbose_name='使用 TLS')

    class Meta:
        verbose_name = 'Sync2Pod 全局配置'

    @classmethod
    def get(cls) -> 'Sync2PodConfig':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
