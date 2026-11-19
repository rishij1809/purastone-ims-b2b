from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core Infrastructure & RBAC'

    def ready(self):
        # Register automated audit signals and model event listeners
        try:
            import core.signals  # noqa: F401
        except ImportError:
            pass
