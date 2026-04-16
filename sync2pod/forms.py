from pathlib import Path

from django import forms

from .models import Sync2PodConfig, Sync2PodTask


class Sync2PodConfigForm(forms.ModelForm):
    smtp_password = forms.CharField(
        required=False,
        label='SMTP 密码',
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
        help_text='留空保持不变',
    )

    class Meta:
        model = Sync2PodConfig
        fields = ['is_tess', 'show_list_log',
                  'alert_email', 'smtp_host', 'smtp_port',
                  'smtp_user', 'smtp_password', 'smtp_use_tls']
        help_texts = {
            'is_tess':       '启用后，所有新建任务默认使用 tess kubectl；已有任务不受影响',
            'show_list_log': '启用后，列表操作栏显示日志按钮，可展开内联日志面板',
            'alert_email':   '任务意外停止时的收件邮箱；为空则不发送',
            'smtp_host':     'e.g. smtp.gmail.com / smtp.exmail.qq.com',
            'smtp_port':     '通常：587（STARTTLS）、465（SSL）、25（无加密）',
            'smtp_user':     '同时作为发件人地址',
        }


class Sync2PodTaskForm(forms.ModelForm):
    class Meta:
        model = Sync2PodTask
        fields = [
            'name', 'pod_type', 'source_dir',
            # k8s params
            'cluster', 'namespace', 'pod_label', 'pod', 'container', 'pod_dir',
            # common
            'is_tess', 'enable_alert', 'interval',
        ]
        widgets = {
            'name':       forms.TextInput(attrs={'placeholder': 'e.g. api-sync'}),
            'pod_type':   forms.Select(),
            'source_dir': forms.TextInput(attrs={'placeholder': '/Users/you/project/src'}),
            'cluster':    forms.TextInput(attrs={'placeholder': '（可选，留空使用当前 kubeconfig 上下文）'}),
            'namespace':  forms.TextInput(attrs={'placeholder': 'default'}),
            'pod_label':  forms.TextInput(attrs={'placeholder': 'app=myapi,env=dev'}),
            'pod':        forms.TextInput(attrs={'placeholder': 'my-pod-7d8f9-xxxx（pod_label 为空时使用）'}),
            'container':  forms.TextInput(attrs={'placeholder': '（可选，多容器时填写）'}),
            'pod_dir':    forms.TextInput(attrs={'placeholder': '/app/src'}),
        }
        help_texts = {
            'name':      '唯一标识，用于日志文件目录名',
            'pod_type':  '',
            'cluster':   'kubeconfig 中的集群名称，留空使用当前上下文',
            'namespace': 'Kubernetes 命名空间，默认为 default',
            'pod_label': '标签选择器，优先级高于 Pod 名称；要求匹配到唯一 Running Pod',
            'pod':       'Pod 名称，pod_label 为空时使用；可通过 kubectl get pods 查看',
            'container': '多容器 Pod 时需指定容器名，单容器可留空',
            'pod_dir':   'Pod 内目标路径，本地文件将同步到此目录',
            'interval':  '轮询间隔（秒），fswatch 不可用时使用',
        }

    def clean_source_dir(self):
        value = self.cleaned_data.get('source_dir', '').strip()
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise forms.ValidationError(f'源目录不存在: {path}')
        return str(path)

    def clean_namespace(self):
        return self.cleaned_data.get('namespace', 'default').strip() or 'default'

    def clean_pod_dir(self):
        value = self.cleaned_data.get('pod_dir', '').strip()
        if not value:
            raise forms.ValidationError('Pod 内目标路径不能为空')
        return value

    def clean(self):
        cleaned = super().clean()
        pod_type  = cleaned.get('pod_type')
        pod_name  = (cleaned.get('pod') or '').strip()
        pod_label = (cleaned.get('pod_label') or '').strip()

        if pod_type == Sync2PodTask.POD_TYPE_K8S:
            if not pod_name and not pod_label:
                raise forms.ValidationError(
                    'Kubernetes 模式下必须填写「Pod 名称」或「Pod 标签选择器」（至少一项）'
                )
        elif pod_type == Sync2PodTask.POD_TYPE_DOCKER:
            raise forms.ValidationError('Docker 容器同步功能尚未实现，敬请期待')

        return cleaned
