from django.db.models import F, Q
from django_filters import rest_framework as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    """Фильтры каталога.

    `filterset_fields = ['category', 'seller']` раньше молча игнорировал `?min_price=…`
    и `?is_ad=…` (200 OK без фильтрации) — фронт не мог заметить, что фильтр не применился.
    """

    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte", label="Цена от")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte", label="Цена до")
    min_rating = filters.NumberFilter(field_name="rating", lookup_expr="gte", label="Рейтинг от")
    is_ad = filters.BooleanFilter(label="Только рекламные / только обычные")
    discounted = filters.BooleanFilter(method="filter_discounted", label="Только со скидкой")
    category = filters.NumberFilter(field_name="category_id", label="ID категории")
    category_slug = filters.CharFilter(field_name="category__slug", label="Slug категории")
    seller = filters.NumberFilter(field_name="seller_id", label="ID продавца")
    search = filters.CharFilter(method="filter_search", label="Поиск по названию/описанию")

    class Meta:
        model = Product
        fields = [
            "category",
            "category_slug",
            "seller",
            "is_ad",
            "discounted",
            "min_price",
            "max_price",
            "min_rating",
        ]

    def filter_discounted(self, queryset, name, value):
        if value is None:
            return queryset
        discounted = Q(old_price__isnull=False) & Q(old_price__gt=F("price"))
        return queryset.filter(discounted) if value else queryset.exclude(discounted)

    def filter_search(self, queryset, name, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(Q(title__icontains=value) | Q(description__icontains=value))
