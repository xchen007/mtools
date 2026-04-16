import json
import re
import subprocess
import sys
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import Sync2PodConfigForm, Sync2PodTaskForm
from .models import Sync2PodConfig, Sync2PodTask

SYNC2POD_RUNNER = Path(__file__).resolve().parent / 'runner.py'
ANSI_ESCAPE     = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
LOG_TAIL_LINES  = 200


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)


def _get_kubeconfig_context(is_tess: bool = False) -> dict | None:
    """读取当前 kubeconfig 上下文信息（context 名、cluster、namespace）。
    is_tess=True 时使用 tess kubectl，否则使用 kubectl。
    kubectl/tess 不可用或出错时返回 None。
    """
    try:
        from subprocess import Popen, PIPE
        base_cmd = ["tess", "kubectl"] if is_tess else ["kubectl"]
        p = Popen(
            base_cmd + ["config", "view", "-o", "json", "--allow-missing-template-keys=true"],
            stdin=PIPE, stdout=PIPE, stderr=PIPE,
        )
        output, _ = p.communicate(timeout=5)
        if p.returncode != 0:
            return None

        data = json.loads(output)
        current = data.get('current-context', '')

        context_map: dict[str, dict] = {}
        for ctx in data.get('contexts') or []:
            name = ctx.get('name', '')
            ctx_data = ctx.get('context') or {}
            context_map[name] = {
                'cluster':   ctx_data.get('cluster', '') or name,
                'namespace': ctx_data.get('namespace', '') or 'default',
            }

        info = context_map.get(current, {})
        return {
            'context':   current,
            'cluster':   info.get('cluster', current),
            'namespace': info.get('namespace', 'default'),
            'is_tess':   is_tess,
        }
    except Exception:
        return None


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ''
    with open(path, 'rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 1024 * 50))
        raw = f.read().decode('utf-8', errors='replace')
    return '\n'.join(raw.splitlines()[-n:])


def sync2pod_list(request):
    tasks = list(Sync2PodTask.objects.all())
    for task in tasks:
        task.sync_status()
    config = Sync2PodConfig.get()
    return render(request, 'sync2pod/list.html', {'tasks': tasks, 'config': config})


def sync2pod_create(request):
    if request.method == 'POST':
        form = Sync2PodTaskForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('sync2pod_list')
        is_tess = request.POST.get('is_tess') == 'on'
    else:
        config = Sync2PodConfig.get()
        form = Sync2PodTaskForm(initial={'is_tess': config.is_tess})
        is_tess = config.is_tess
    return render(request, 'sync2pod/create.html', {
        'form': form,
        'kube_ctx': _get_kubeconfig_context(is_tess=is_tess),
    })


def sync2pod_settings(request):
    """保留旧 URL，重定向到统一设置页。"""
    return redirect('/settings/?tab=sync2pod')


def sync2pod_edit(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    if task.status == Sync2PodTask.STATUS_RUNNING:
        return redirect('sync2pod_detail', task_id=task_id)

    if request.method == 'POST':
        form = Sync2PodTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return redirect('sync2pod_detail', task_id=task_id)
        is_tess = request.POST.get('is_tess') == 'on'
    else:
        form = Sync2PodTaskForm(instance=task)
        is_tess = task.is_tess
    return render(request, 'sync2pod/edit.html', {
        'form': form,
        'task': task,
        'kube_ctx': _get_kubeconfig_context(is_tess=is_tess),
    })


def sync2pod_kube_context(request):
    """AJAX: 返回当前 kubeconfig 上下文信息。?tess=1 使用 tess kubectl。"""
    is_tess = request.GET.get('tess') == '1'
    ctx = _get_kubeconfig_context(is_tess=is_tess)
    if ctx is None:
        cmd = 'tess kubectl' if is_tess else 'kubectl'
        return JsonResponse({'error': f'{cmd} 不可用或未配置'}, status=200)
    return JsonResponse(ctx)


def sync2pod_detail(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    task.sync_status()
    return render(request, 'sync2pod/detail.html', {'task': task})


@require_POST
def sync2pod_start(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    task.sync_status()
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if task.status == Sync2PodTask.STATUS_RUNNING:
        return JsonResponse({'status': 'running', 'pid': task.pid}) if ajax else redirect('sync2pod_list')

    if task.pod_type == Sync2PodTask.POD_TYPE_DOCKER:
        task.status = Sync2PodTask.STATUS_ERROR
        task.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'status': 'error', 'error': 'Docker 未实现'}) if ajax else redirect('sync2pod_list')

    source = Path(task.source_dir).expanduser()
    if not source.is_dir():
        task.status = Sync2PodTask.STATUS_ERROR
        task.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'status': 'error', 'error': f'源目录不存在: {source}'}) if ajax else redirect('sync2pod_list')

    log_file = task.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(SYNC2POD_RUNNER),
        task.source_dir,
        task.pod or "",
        task.pod_dir,
        '--namespace', task.namespace,
        '--interval',  str(task.interval),
        '--name',      task.name,
    ]
    if task.pod_label:
        cmd += ['--pod-label', task.pod_label]
    if task.cluster:
        cmd += ['--cluster', task.cluster]
    if task.container:
        cmd += ['--container', task.container]
    if task.is_tess:
        cmd += ['--tess']

    with open(log_file, 'a') as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, start_new_session=True)

    task.pid = proc.pid
    task.status = Sync2PodTask.STATUS_RUNNING
    task.save(update_fields=['pid', 'status', 'updated_at'])
    if ajax:
        return JsonResponse({'status': 'running', 'pid': task.pid})
    return redirect('sync2pod_list')


@require_POST
def sync2pod_stop(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    task.terminate()
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if ajax:
        return JsonResponse({'status': 'stopped'})
    return redirect('sync2pod_list')


@require_POST
def sync2pod_delete(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    if task.is_process_running():
        task.terminate()
    task.delete()
    return redirect('sync2pod_list')


def sync2pod_logs(request, task_id):
    task = get_object_or_404(Sync2PodTask, id=task_id)
    task.sync_status()
    raw = _tail(task.log_file, LOG_TAIL_LINES)
    return JsonResponse({
        'logs':   _strip_ansi(raw),
        'status': task.status,
        'pid':    task.pid,
    })


def sync2pod_status_all(request):
    """返回所有任务的实时状态，供列表页轮询使用。"""
    tasks = list(Sync2PodTask.objects.all())
    result = {}
    for task in tasks:
        task.sync_status()
        result[task.id] = {'status': task.status, 'pid': task.pid}
    return JsonResponse(result)
