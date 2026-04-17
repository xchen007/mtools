import re
import threading
import time

from channels.generic.websocket import JsonWebsocketConsumer

from .models import BisyncTarget

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


class BisyncTargetLogConsumer(JsonWebsocketConsumer):
    """Stream log + status for a single BisyncTarget via WebSocket."""

    def connect(self):
        self.target_id = int(self.scope['url_route']['kwargs']['target_id'])
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
                target = BisyncTarget.objects.select_related('task').get(pk=self.target_id)
                target.sync_status()
                mtime = target.log_mtime
                ts = mtime.timestamp() if mtime else None
                if ts != last_mtime:
                    last_mtime = ts
                    raw = _tail(target.log_file, LOG_TAIL_LINES)
                    self.send_json({
                        'type': 'log',
                        'logs': _strip_ansi(raw),
                        'status': target.status,
                        'pid': target.pid,
                        'log_mtime': ts,
                    })
                else:
                    # Still push status updates even if log unchanged
                    self.send_json({
                        'type': 'status',
                        'status': target.status,
                        'pid': target.pid,
                    })
            except BisyncTarget.DoesNotExist:
                self.send_json({'type': 'error', 'message': 'target not found'})
                break
            except Exception:
                pass
            self._stop.wait(POLL_INTERVAL)
