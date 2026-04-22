from rest_framework import serializers

from .models import Sync2PodConfig, Sync2PodTask


class Sync2PodTaskSerializer(serializers.ModelSerializer):
    log_tail = serializers.SerializerMethodField()

    class Meta:
        model = Sync2PodTask
        fields = [
            'id', 'name', 'pod_type', 'source_dir',
            'cluster', 'namespace', 'pod_label', 'pod', 'container', 'pod_dir',
            'is_tess', 'interval', 'enable_alert',
            'status', 'pid', 'last_sync_at',
            'created_at', 'updated_at',
            'log_tail',
        ]
        read_only_fields = ['id', 'status', 'pid', 'last_sync_at', 'created_at', 'updated_at', 'log_tail']

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

    def validate_source_dir(self, value):
        from pathlib import Path
        path = Path(value.strip()).expanduser().resolve()
        if not path.is_dir():
            raise serializers.ValidationError(f'源目录不存在: {path}')
        return str(path)

    def validate_namespace(self, value):
        return (value or 'default').strip() or 'default'

    def validate_pod_dir(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Pod 内目标路径不能为空')
        return value

    def validate(self, data):
        pod_type = data.get('pod_type', getattr(self.instance, 'pod_type', Sync2PodTask.POD_TYPE_K8S))
        pod = (data.get('pod') or getattr(self.instance, 'pod', '') or '').strip()
        pod_label = (data.get('pod_label') or getattr(self.instance, 'pod_label', '') or '').strip()
        if pod_type == Sync2PodTask.POD_TYPE_K8S and not pod and not pod_label:
            raise serializers.ValidationError(
                'Kubernetes 模式下必须填写 pod 或 pod_label（至少一项）'
            )
        if pod_type == Sync2PodTask.POD_TYPE_DOCKER:
            raise serializers.ValidationError('Docker 容器同步功能尚未实现')
        return data


class Sync2PodConfigSerializer(serializers.ModelSerializer):
    smtp_password = serializers.CharField(
        required=False, allow_blank=True, write_only=False,
        style={'input_type': 'password'},
    )

    class Meta:
        model = Sync2PodConfig
        fields = [
            'is_tess', 'show_list_log',
            'custom_kubectl_cmd', 'custom_docker_cmd',
            'alert_email', 'smtp_host', 'smtp_port',
            'smtp_user', 'smtp_password', 'smtp_use_tls',
        ]
