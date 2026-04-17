import re
import subprocess
import sys
from pathlib import Path

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ViewSet

from .models import BisyncTarget, BisyncTask
from .serializers import BisyncTargetSerializer, BisyncTargetWriteSerializer, BisyncTaskSerializer

BISYNC_RUNNER = Path(__file__).resolve().parent / 'runner.py'
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
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


class BisyncTaskViewSet(ModelViewSet):
    queryset = BisyncTask.objects.prefetch_related('targets').all()
    serializer_class = BisyncTaskSerializer

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        for target in task.targets.all():
            if target.is_process_running():
                target.terminate()
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def start_all(self, request, pk=None):
        task = self.get_object()
        source = Path(task.source_dir).expanduser()
        results = []
        for target in task.targets.all():
            target.sync_status()
            if target.status == BisyncTarget.STATUS_RUNNING:
                results.append({'id': target.id, 'result': 'already_running'})
                continue
            if not source.is_dir():
                target.status = BisyncTarget.STATUS_ERROR
                target.save(update_fields=['status', 'updated_at'])
                results.append({'id': target.id, 'result': 'error', 'reason': 'source_missing'})
                continue
            log_file = target.log_file
            log_file.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                sys.executable, str(BISYNC_RUNNER),
                task.source_dir, target.target_dir,
                '--name', target.runner_name,
                '--interval', str(task.interval),
                '--debounce', str(task.debounce_seconds),
            ]
            for pat in task.exclude_patterns_list:
                cmd += ['--exclude', pat]
            with open(log_file, 'a') as lf:
                proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, start_new_session=True)
            target.pid = proc.pid
            target.status = BisyncTarget.STATUS_RUNNING
            target.save(update_fields=['pid', 'status', 'updated_at'])
            results.append({'id': target.id, 'result': 'started', 'pid': proc.pid})
        return Response(results)

    @action(detail=True, methods=['post'])
    def stop_all(self, request, pk=None):
        task = self.get_object()
        results = []
        for target in task.targets.all():
            if target.is_process_running():
                target.terminate()
                results.append({'id': target.id, 'result': 'stopped'})
            else:
                results.append({'id': target.id, 'result': 'not_running'})
        return Response(results)

    @action(detail=True, methods=['get', 'post'], url_path='targets')
    def targets(self, request, pk=None):
        task = self.get_object()
        if request.method == 'GET':
            targets = list(task.targets.all())
            for t in targets:
                t.sync_status()
            return Response(BisyncTargetSerializer(targets, many=True).data)
        # POST — add target
        serializer = BisyncTargetWriteSerializer(data=request.data)
        if serializer.is_valid():
            target = serializer.save(task=task)
            return Response(BisyncTargetSerializer(target).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='open')
    def open_path(self, request):
        path = request.GET.get('path', '').strip()
        if path and Path(path).is_dir():
            subprocess.Popen(['open', path])
        return Response({'ok': True})


class BisyncTargetViewSet(ViewSet):
    def _get_target(self, pk):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(BisyncTarget, pk=pk)

    def destroy(self, request, pk=None):
        target = self._get_target(pk)
        if target.is_process_running():
            target.terminate()
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def start(self, request, pk=None):
        target = self._get_target(pk)
        target.sync_status()
        if target.status == BisyncTarget.STATUS_RUNNING:
            return Response({'status': 'already_running', 'pid': target.pid})

        source = Path(target.task.source_dir).expanduser()
        if not source.is_dir():
            target.status = BisyncTarget.STATUS_ERROR
            target.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'error', 'reason': 'source_missing'},
                            status=status.HTTP_400_BAD_REQUEST)

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
        return Response({'status': 'running', 'pid': proc.pid})

    def stop(self, request, pk=None):
        target = self._get_target(pk)
        target.terminate()
        return Response({'status': 'stopped'})

    def reset(self, request, pk=None):
        target = self._get_target(pk)
        state_file = Path.home() / '.bisync' / target.runner_name / 'state.json'
        if state_file.exists():
            state_file.unlink()
        return Response({'ok': True})

    def logs(self, request, pk=None):
        target = self._get_target(pk)
        target.sync_status()
        raw = _tail(target.log_file, LOG_TAIL_LINES)
        return Response({
            'logs': _strip_ansi(raw),
            'status': target.status,
            'pid': target.pid,
        })

    def retrieve(self, request, pk=None):
        target = self._get_target(pk)
        target.sync_status()
        return Response(BisyncTargetSerializer(target).data)
