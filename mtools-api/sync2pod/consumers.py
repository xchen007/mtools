import re
import threading

from channels.generic.websocket import JsonWebsocketConsumer

from .models import Sync2PodTask

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
POLL_INTERVAL = 1.0
LOG_TAIL_LINES = 200


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)


def _tail(path, n: int) -> str:
    if not path.exists():
        return ''
    with open(path, 'rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 1024 * 50))
        raw = f.read().decode('utf-8', errors='replace')
    return '\n'.join(raw.splitlines()[-n:])


class Sync2PodTaskLogConsumer(JsonWebsocketConsumer):
    """Stream log + status for a single Sync2PodTask via WebSocket."""

    def connect(self):
        self.task_id = int(self.scope['url_route']['kwargs']['task_id'])
        self._stop = threading.Event()
        self.accept()
        t = threading.Thread(target=self._stream, daemon=True)
        t.start()

    def disconnect(self, close_code):
        self._stop.set()

    def _stream(self):
        last_mtime = None
        while not self._stop.is_set():
            try:
                task = Sync2PodTask.objects.get(pk=self.task_id)
                task.sync_status()
                p = task.log_file
                ts = p.stat().st_mtime if p.exists() else None
                if ts != last_mtime:
                    last_mtime = ts
                    raw = _tail(p, LOG_TAIL_LINES)
                    self.send_json({
                        'type': 'log',
                        'logs': _strip_ansi(raw),
                        'status': task.status,
                        'pid': task.pid,
                        'log_mtime': ts,
                    })
                else:
                    self.send_json({
                        'type': 'status',
                        'status': task.status,
                        'pid': task.pid,
                    })
            except Sync2PodTask.DoesNotExist:
                self.send_json({'type': 'error', 'message': 'task not found'})
                break
            except Exception:
                pass
            self._stop.wait(POLL_INTERVAL)
