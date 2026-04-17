# Generated migration: add BisyncTarget, migrate data, remove old fields from BisyncTask

import django.db.models.deletion
from django.db import migrations, models


def forward_migrate_targets(apps, schema_editor):
    """把旧 BisyncTask 的 target_dir/status/pid 迁移到新 BisyncTarget 表。"""
    BisyncTask = apps.get_model('bisync', 'BisyncTask')
    BisyncTarget = apps.get_model('bisync', 'BisyncTarget')
    for task in BisyncTask.objects.all():
        if task.target_dir:
            BisyncTarget.objects.create(
                task=task,
                target_dir=task.target_dir,
                status=task.status if task.status in ('stopped', 'running', 'error') else 'stopped',
                pid=task.pid if task.status == 'running' else None,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('bisync', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BisyncTarget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('target_dir', models.CharField(max_length=500, verbose_name='目标目录')),
                ('status', models.CharField(
                    choices=[('stopped', '已停止'), ('running', '运行中'), ('error', '错误')],
                    default='stopped', max_length=20, verbose_name='状态')),
                ('pid', models.IntegerField(blank=True, null=True, verbose_name='进程ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('task', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='targets',
                    to='bisync.bisynctask',
                    verbose_name='所属任务',
                )),
            ],
            options={
                'verbose_name': 'Bisync 目标',
                'ordering': ['created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='bisynctarget',
            unique_together={('task', 'target_dir')},
        ),
        migrations.RunPython(forward_migrate_targets, migrations.RunPython.noop),
        migrations.RemoveField(model_name='BisyncTask', name='target_dir'),
        migrations.RemoveField(model_name='BisyncTask', name='status'),
        migrations.RemoveField(model_name='BisyncTask', name='pid'),
    ]
