from django.apps import AppConfig


class ProductsConfig(AppConfig):
    name = "apps.products"
    label = "products"
    verbose_name = "Каталог товаров"
    default_auto_field = "django.db.models.BigAutoField"
