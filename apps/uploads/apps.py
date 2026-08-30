from django.apps import AppConfig


class UploadsConfig(AppConfig):
    name = "apps.uploads"
    label = "uploads"
    verbose_name = "Загрузка файлов"
    default_auto_field = "django.db.models.BigAutoField"
