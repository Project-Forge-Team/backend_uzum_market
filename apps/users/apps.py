from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "apps.users"
    label = "users"
    verbose_name = "Пользователи и авторизация"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Регистрирует OpenApiAuthenticationExtension для нашего аутентификатора,
        # иначе spectacular не знает, как описать cookie/Bearer-безопасность.
        from . import schema  # noqa: F401
