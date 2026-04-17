from rest_framework import serializers

from .models import BisyncTarget, BisyncTask


class BisyncTargetSerializer(serializers.ModelSerializer):
    log_tail = serializers.SerializerMethodField()
    log_mtime = serializers.SerializerMethodField()

    class Meta:
        model = BisyncTarget
        fields = [
            'id', 'task', 'target_dir', 'status', 'pid',
            'created_at', 'updated_at', 'log_tail', 'log_mtime',
        ]
        read_only_fields = ['id', 'status', 'pid', 'created_at', 'updated_at', 'log_tail', 'log_mtime']

    def get_log_tail(self, obj) -> str:
        import re
        ansi = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        p = obj.log_file
        if not p.exists():
            return ''
        with open(p, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 1024 * 10))
            raw = f.read().decode('utf-8', errors='replace')
        tail = '\n'.join(raw.splitlines()[-3:])
        return ansi.sub('', tail)

    def get_log_mtime(self, obj):
        mtime = obj.log_mtime
        return mtime.timestamp() if mtime else None


class BisyncTargetWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BisyncTarget
        fields = ['target_dir']

    def validate_target_dir(self, value):
        from pathlib import Path
        value = value.strip()
        path = Path(value).expanduser().resolve()
        if not path.parent.exists():
            raise serializers.ValidationError(f'父路径不存在: {path.parent}')
        return str(path)


class BisyncTaskSerializer(serializers.ModelSerializer):
    targets = BisyncTargetSerializer(many=True, read_only=True)

    class Meta:
        model = BisyncTask
        fields = [
            'id', 'name', 'source_dir', 'interval', 'debounce_seconds',
            'exclude_patterns', 'created_at', 'updated_at', 'targets',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_source_dir(self, value):
        from pathlib import Path
        path = Path(value.strip()).expanduser().resolve()
        if not path.is_dir():
            raise serializers.ValidationError(f'源目录不存在: {path}')
        return str(path)
