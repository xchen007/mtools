from django.apps import AppConfig


class BisyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bisync'
    verbose_name = '双向同步'
