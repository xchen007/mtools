import json
import re
import subprocess
import sys
from pathlib import Path

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ViewSet

from .models import Sync2PodConfig, Sync2PodTask
from .serializers import Sync2PodConfigSerializer, Sync2PodTaskSerializer

SYNC2POD_RUNNER = Path(__file__).resolve().parent / 'runner.py'
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
LOG_TAIL_LINES = 200


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)


def _clear_log_file(log_file: Path) -> None:
    """Clear log file content."""
    try:
        if log_file.exists():
            log_file.unlink()  # Delete the file
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.touch()  # Create empty file
    except Exception:
        pass  # Ignore errors during cleanup


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ''
    with open(path, 'rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 1024 * 50))
        raw = f.read().decode('utf-8', errors='replace')
    return '\n'.join(raw.splitlines()[-n:])


def _get_kubeconfig_context(is_tess: bool = False) -> dict | None:
    try:
        base_cmd = ['tess', 'kubectl'] if is_tess else ['kubectl']
        from subprocess import PIPE, Popen
        p = Popen(
            base_cmd + ['config', 'view', '-o', 'json', '--allow-missing-template-keys=true'],
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
                'cluster': ctx_data.get('cluster', '') or name,
                'namespace': ctx_data.get('namespace', '') or 'default',
            }
        info = context_map.get(current, {})
        return {
            'context': current,
            'cluster': info.get('cluster', current),
            'namespace': info.get('namespace', 'default'),
            'is_tess': is_tess,
        }
    except Exception:
        return None


class Sync2PodTaskViewSet(ModelViewSet):
    queryset = Sync2PodTask.objects.all()
    serializer_class = Sync2PodTaskSerializer

    def list(self, request, *args, **kwargs):
        tasks = list(self.get_queryset())
        for task in tasks:
            task.sync_status()
        return Response(Sync2PodTaskSerializer(tasks, many=True).data)

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        if task.is_process_running():
            task.terminate()
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        task = self.get_object()
        task.sync_status()
        if task.status == Sync2PodTask.STATUS_RUNNING:
            return Response({'status': 'running', 'pid': task.pid})
        if task.pod_type == Sync2PodTask.POD_TYPE_DOCKER:
            task.status = Sync2PodTask.STATUS_ERROR
            task.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'error', 'reason': 'docker_not_implemented'},
                            status=status.HTTP_400_BAD_REQUEST)
        source = Path(task.source_dir).expanduser()
        if not source.is_dir():
            task.status = Sync2PodTask.STATUS_ERROR
            task.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'error', 'reason': f'source_missing: {source}'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Clear log file before starting
        log_file = task.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _clear_log_file(log_file)
        cmd = [
            sys.executable, str(SYNC2POD_RUNNER),
            task.source_dir,
            task.pod or '',
            task.pod_dir,
            '--namespace', task.namespace,
            '--interval', str(task.interval),
            '--name', task.name,
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
        return Response({'status': 'running', 'pid': task.pid})

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        task = self.get_object()
        task.terminate()

        # Clear log file after stopping
        _clear_log_file(task.log_file)

        return Response({'status': 'stopped'})

    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """Restart task: stop -> clear logs -> start."""
        task = self.get_object()

        # Stop if running
        if task.status == Sync2PodTask.STATUS_RUNNING:
            task.terminate()

        # Clear log file
        _clear_log_file(task.log_file)

        # Start the task (reuse start logic)
        if task.pod_type == Sync2PodTask.POD_TYPE_DOCKER:
            task.status = Sync2PodTask.STATUS_ERROR
            task.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'error', 'reason': 'docker_not_implemented'},
                            status=status.HTTP_400_BAD_REQUEST)

        source = Path(task.source_dir).expanduser()
        if not source.is_dir():
            task.status = Sync2PodTask.STATUS_ERROR
            task.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'error', 'reason': f'source_missing: {source}'},
                            status=status.HTTP_400_BAD_REQUEST)

        log_file = task.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, str(SYNC2POD_RUNNER),
            task.source_dir,
            task.pod or '',
            task.pod_dir,
            '--namespace', task.namespace,
            '--interval', str(task.interval),
            '--name', task.name,
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

        return Response({'status': 'restarted', 'pid': task.pid})

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        task = self.get_object()
        task.sync_status()
        raw = _tail(task.log_file, LOG_TAIL_LINES)
        return Response({
            'logs': _strip_ansi(raw),
            'status': task.status,
            'pid': task.pid,
        })


class Sync2PodKubeContextView(ViewSet):
    def list(self, request):
        is_tess = request.GET.get('tess') == '1'
        ctx = _get_kubeconfig_context(is_tess=is_tess)
        if ctx is None:
            cmd = 'tess kubectl' if is_tess else 'kubectl'
            return Response({'error': f'{cmd} 不可用或未配置'})
        return Response(ctx)


class Sync2PodConfigView(ViewSet):
    def list(self, request):
        cfg = Sync2PodConfig.get()
        return Response(Sync2PodConfigSerializer(cfg).data)

    def partial_update(self, request, pk=None):
        cfg = Sync2PodConfig.get()
        serializer = Sync2PodConfigSerializer(cfg, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
