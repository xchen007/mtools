import re
import subprocess
import sys
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BisyncTargetForm, BisyncTaskForm
from .models import BisyncTarget, BisyncTask

BISYNC_RUNNER = Path(__file__).resolve().parent / 'runner.py'
ANSI_ESCAPE   = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
LOG_TAIL_LINES = 200


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ''
    with open(path, 'rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 1024 * 50))
        raw = f.read().decode('utf-8', errors='replace')
    return '\n'.join(raw.splitlines()[-n:])


# ────────── Task views ──────────

def bisync_list(request):
    tasks = list(BisyncTask.objects.prefetch_related('targets').all())
    for task in tasks:
        for t in task.targets.all():
            t.sync_status()
            t.log_tail = _strip_ansi(_tail(t.log_file, 2))
    return render(request, 'bisync/list.html', {'tasks': tasks})


def bisync_create(request):
    if request.method == 'POST':
        form = BisyncTaskForm(request.POST)
        if form.is_valid():
            task = form.save()
            return redirect('bisync_detail', task_id=task.id)
    else:
        form = BisyncTaskForm()
    return render(request, 'bisync/create.html', {'form': form})


def bisync_detail(request, task_id):
    task = get_object_or_404(BisyncTask, id=task_id)
    targets = list(task.targets.all())
    for t in targets:
        t.sync_status()
    form = BisyncTargetForm()
    task_form = BisyncTaskForm(instance=task)
    return render(request, 'bisync/detail.html', {
        'task': task, 'targets': targets,
        'form': form, 'task_form': task_form,
    })


def bisync_edit_task(request, task_id):
    task = get_object_or_404(BisyncTask, id=task_id)
    if request.method == 'POST':
        form = BisyncTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
    return redirect('bisync_detail', task_id=task_id)


@require_POST
def bisync_delete_task(request, task_id):
    task = get_object_or_404(BisyncTask, id=task_id)
    for target in task.targets.all():
        if target.is_process_running():
            target.terminate()
    task.delete()
    return redirect('bisync_list')


@require_POST
def bisync_add_target(request, task_id):
    task = get_object_or_404(BisyncTask, id=task_id)
    form = BisyncTargetForm(request.POST)
    if form.is_valid():
        target = form.save(commit=False)
        target.task = task
        target.save()
    return redirect('bisync_detail', task_id=task.id)


@require_POST
def bisync_start_all(request, task_id):
    """启动任务下所有未运行的目标。"""
    task = get_object_or_404(BisyncTask, id=task_id)
    source = Path(task.source_dir).expanduser()
    for target in task.targets.all():
        target.sync_status()
        if target.status == BisyncTarget.STATUS_RUNNING:
            continue
        if not source.is_dir():
            target.status = BisyncTarget.STATUS_ERROR
            target.save(update_fields=['status', 'updated_at'])
            continue
        log_file = target.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(BISYNC_RUNNER),
            task.source_dir, target.target_dir,
            '--name', target.runner_name,
            '--interval', str(task.interval),
        ]
        with open(log_file, 'a') as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, start_new_session=True)
        target.pid = proc.pid
        target.status = BisyncTarget.STATUS_RUNNING
        target.save(update_fields=['pid', 'status', 'updated_at'])
    return redirect('bisync_list')


@require_POST
def bisync_stop_all(request, task_id):
    """停止任务下所有运行中的目标。"""
    task = get_object_or_404(BisyncTask, id=task_id)
    for target in task.targets.all():
        if target.is_process_running():
            target.terminate()
    return redirect('bisync_list')


@require_POST
def target_start(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    target.sync_status()

    if target.status == BisyncTarget.STATUS_RUNNING:
        return redirect('bisync_detail', task_id=target.task_id)

    source = Path(target.task.source_dir).expanduser()
    if not source.is_dir():
        target.status = BisyncTarget.STATUS_ERROR
        target.save(update_fields=['status', 'updated_at'])
        return redirect('bisync_detail', task_id=target.task_id)

    log_file = target.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(BISYNC_RUNNER),
        target.task.source_dir, target.target_dir,
        '--name', target.runner_name,
        '--interval', str(target.task.interval),
        '--debounce', str(target.task.debounce_seconds),
    ]
    for pat in target.task.exclude_patterns_list:
        cmd += ['--exclude', pat]

    with open(log_file, 'a') as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, start_new_session=True)

    target.pid = proc.pid
    target.status = BisyncTarget.STATUS_RUNNING
    target.save(update_fields=['pid', 'status', 'updated_at'])
    return redirect('bisync_detail', task_id=target.task_id)


@require_POST
def target_stop(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    target.terminate()
    return redirect('bisync_detail', task_id=target.task_id)


@require_POST
def target_delete(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    task_id = target.task_id
    if target.is_process_running():
        target.terminate()
    target.delete()
    return redirect('bisync_detail', task_id=task_id)


@require_POST
def target_reset(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    state_file = Path.home() / '.bisync' / target.runner_name / 'state.json'
    if state_file.exists():
        state_file.unlink()
    return redirect('bisync_detail', task_id=target.task_id)


def target_log_page(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    target.sync_status()
    return render(request, 'bisync/target_logs.html', {'target': target})


def target_logs_json(request, target_id):
    target = get_object_or_404(BisyncTarget, id=target_id)
    target.sync_status()
    raw = _tail(target.log_file, LOG_TAIL_LINES)
    return JsonResponse({
        'logs': _strip_ansi(raw),
        'status': target.status,
        'pid': target.pid,
    })


def bisync_status_all(request):
    """返回所有目标的实时状态（含最后 N 行日志），供列表页轮询使用。"""
    try:
        lines = max(1, min(50, int(request.GET.get('lines', 2))))
    except (ValueError, TypeError):
        lines = 2
    targets = list(BisyncTarget.objects.select_related('task').all())
    result = {}
    for t in targets:
        t.sync_status()
        tail = _strip_ansi(_tail(t.log_file, lines))
        mtime = t.log_mtime
        result[t.id] = {
            'status': t.status,
            'pid': t.pid,
            'task_id': t.task_id,
            'log_tail': tail,
            'log_mtime': mtime.timestamp() if mtime else None,
        }
    return JsonResponse(result)


def bisync_open_path(request):
    """在 macOS Finder 中打开指定本地目录（GET ?path=...）。"""
    path = request.GET.get('path', '').strip()
    if path and Path(path).is_dir():
        subprocess.Popen(['open', path])
    # 返回到来源页
    return redirect(request.META.get('HTTP_REFERER', '/bisync/'))
