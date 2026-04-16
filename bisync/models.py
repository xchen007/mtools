import os
import signal
from pathlib import Path

from django.db import models


class BisyncTask(models.Model):
    name             = models.CharField(max_length=100, unique=True, verbose_name='任务名称')
    source_dir       = models.CharField(max_length=500, verbose_name='源目录')
    interval         = models.IntegerField(default=3, verbose_name='轮询间隔(秒)')
    debounce_seconds = models.FloatField(default=1.0, verbose_name='防抖延迟(秒)',
                                         help_text='检测到变更后延迟多少秒再同步（默认 1.0）')
    exclude_patterns = models.TextField(blank=True, default='', verbose_name='排除模式',
                                        help_text='每行一个 glob 模式，如 __pycache__  *.pyc  node_modules')
    created_at       = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at       = models.DateTimeField(auto_now=True,     verbose_name='更新时间')

    class Meta:
        verbose_name = 'Bisync 任务'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def exclude_patterns_list(self) -> list[str]:
        """返回非空排除模式列表。"""
        return [p.strip() for p in self.exclude_patterns.splitlines() if p.strip()]

    def has_running_targets(self) -> bool:
        return self.targets.filter(status=BisyncTarget.STATUS_RUNNING).exists()


class BisyncTarget(models.Model):
    STATUS_STOPPED = 'stopped'
    STATUS_RUNNING = 'running'
    STATUS_ERROR   = 'error'
    STATUS_CHOICES = [
        (STATUS_STOPPED, '已停止'),
        (STATUS_RUNNING, '运行中'),
        (STATUS_ERROR,   '错误'),
    ]

    task       = models.ForeignKey(BisyncTask, on_delete=models.CASCADE,
                                   related_name='targets', verbose_name='所属任务')
    target_dir = models.CharField(max_length=500, verbose_name='目标目录')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                  default=STATUS_STOPPED, verbose_name='状态')
    pid        = models.IntegerField(null=True, blank=True, verbose_name='进程ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True,     verbose_name='更新时间')

    class Meta:
        verbose_name = 'Bisync 目标'
        ordering = ['created_at']
        unique_together = [('task', 'target_dir')]

    def __str__(self):
        return f"{self.task.name} → {self.target_dir}"

    @property
    def runner_name(self) -> str:
        """runner --name 参数，决定 state 文件目录名，必须在 save() 之后调用。"""
        return f"{self.task.name}_t{self.id}"

    @property
    def log_file(self) -> Path:
        return Path.home() / '.bisync' / self.task.name / f't{self.id}' / 'output.log'

    @property
    def log_mtime(self):
        """返回 log 文件最后修改时间（aware datetime），不存在则 None。"""
        p = self.log_file
        if p.exists():
            import datetime
            return datetime.datetime.fromtimestamp(p.stat().st_mtime,
                                                   tz=datetime.timezone.utc)
        return None

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
        if self.status == self.STATUS_RUNNING:
            # target dir 已删除 → 立即 terminate
            if not Path(self.target_dir).is_dir():
                self.terminate()
                return True
            if not self.is_process_running():
                self.status = self.STATUS_STOPPED
                self.pid = None
                self.save(update_fields=['status', 'pid', 'updated_at'])
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
