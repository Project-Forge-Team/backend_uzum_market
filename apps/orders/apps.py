from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = "apps.orders"
    label = "orders"
    verbose_name = "Заказы"
    default_auto_field = "django.db.models.BigAutoField"
