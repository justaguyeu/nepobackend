from django.apps import AppConfig
from django.core import checks


class UploadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "uploads"

    def ready(self):
        from .storage import check_key
        checks.register(check_key)
