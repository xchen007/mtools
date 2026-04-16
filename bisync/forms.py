from pathlib import Path

from django import forms

from .models import BisyncTarget, BisyncTask


class BisyncTaskForm(forms.ModelForm):
    class Meta:
        model = BisyncTask
        fields = ['name', 'source_dir', 'interval', 'debounce_seconds', 'exclude_patterns']
        widgets = {
            'name':             forms.TextInput(attrs={'placeholder': 'e.g. scripts-sync'}),
            'source_dir':       forms.TextInput(attrs={'placeholder': '/Users/you/scripts'}),
            'exclude_patterns': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': '__pycache__\n*.pyc\nnode_modules\n.git',
            }),
        }
        help_texts = {
            'name':             '唯一标识，用于状态文件目录名',
            'interval':         '轮询间隔（秒），fswatch 不可用时使用',
            'debounce_seconds': '检测到文件变更后延迟多少秒再触发同步（默认 1.0）',
            'exclude_patterns': '每行一个 glob 模式，匹配的文件/目录不参与同步',
        }

    def clean_source_dir(self):
        value = self.cleaned_data.get('source_dir', '').strip()
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise forms.ValidationError(f'源目录不存在: {path}')
        return str(path)


class BisyncTargetForm(forms.ModelForm):
    class Meta:
        model = BisyncTarget
        fields = ['target_dir']
        widgets = {
            'target_dir': forms.TextInput(attrs={'placeholder': '/Users/you/project/scripts'}),
        }
        help_texts = {
            'target_dir': '初始化时会先删除此目录，再从源目录完整复制',
        }

    def clean_target_dir(self):
        value = self.cleaned_data.get('target_dir', '').strip()
        path = Path(value).expanduser().resolve()
        if not path.parent.exists():
            raise forms.ValidationError(f'目标目录的父路径不存在: {path.parent}')
        return str(path)
