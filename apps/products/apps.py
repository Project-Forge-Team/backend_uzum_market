from django.apps import AppConfig


class ProductsConfig(AppConfig):
    name = "apps.products"
    label = "products"
    verbose_name = "Каталог товаров"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401  (подписка на post_save/post_delete → инвалидация кэша)
