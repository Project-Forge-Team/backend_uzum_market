from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import bump_version
from .models import Category, Product, Seller

_WATCHED = (Product, Category, Seller)


@receiver([post_save, post_delete], dispatch_uid="products.catalog_cache_invalidation")
def invalidate_catalog_cache(sender, **kwargs):
    """Любое изменение каталога сбрасывает версию ключа → списки пересоберутся.

    Один инкремент счётчика вместо перебора ключей; sender не фиксируем, чтобы
    сигнал не пришлось править при каждом добавлении модели каталога.
    """
    if sender in _WATCHED:
        bump_version()
