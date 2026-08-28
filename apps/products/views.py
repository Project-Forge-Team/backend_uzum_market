import logging

from django.conf import settings
from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.exceptions import ValidationError

from .cache import list_cache_key
from .filters import ProductFilter
from .models import Category, Product, Seller
from .pagination import CatalogPagination
from .serializers import CategorySerializer, ProductListSerializer, ProductSerializer, SellerSerializer

logger = logging.getLogger(__name__)

# Параметры, которые наш каталог точно понимает. Всё остальное — 400 вместо молчаливого
# «200 OK, но фильтр не применился».
COMMON_PARAMS = {"page", "page_size", "ordering", "search", "format"}
LIST_PARAMS = {
    "products": COMMON_PARAMS | set(ProductFilter.get_filters().keys()),
    "categories": COMMON_PARAMS | {"search", "ordering"},
    "sellers": COMMON_PARAMS | {"search", "ordering"},
}


class StrictQueryParamsMixin:
    """Отсекаем опечатки в query-параметрах на входе."""

    unknown_params_error = None

    def list(self, request, *args, **kwargs):
        allowed = LIST_PARAMS.get(self.basename_key, COMMON_PARAMS)
        unknown = sorted(key for key in request.query_params if key not in allowed)
        if unknown:
            raise ValidationError(
                {
                    "query": [
                        "Неизвестные параметры: {}. Разрешённые: {}.".format(
                            ", ".join(unknown), ", ".join(sorted(allowed))
                        )
                    ]
                }
            )
        return super().list(request, *args, **kwargs)


class CachedListMixin:
    """Короткий TTL на списки: категории/продавцы меняются редко, а дёргаются на каждый рендер шапки."""

    cache_timeout = settings.CATALOG_CACHE_SECONDS

    def list(self, request, *args, **kwargs):
        if self.cache_timeout <= 0:
            return super().list(request, *args, **kwargs)
        key = list_cache_key(request)
        cached = cache.get(key)
        if cached is not None:
            return self.build_response(cached)
        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(key, response.data, self.cache_timeout)
        return response

    def build_response(self, data):
        from rest_framework.response import Response

        return Response(data)


class BaseReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """Общее для каталога: пагинация, фильтры, поиск, сортировка, кэш списков."""

    pagination_class = CatalogPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]


class CategoryViewSet(StrictQueryParamsMixin, CachedListMixin, BaseReadOnlyViewSet):
    """Категории: список и детали."""

    basename_key = "categories"
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "id"]


class SellerViewSet(StrictQueryParamsMixin, CachedListMixin, BaseReadOnlyViewSet):
    """Продавцы: список и детали."""

    basename_key = "sellers"
    queryset = Seller.objects.all()
    serializer_class = SellerSerializer
    search_fields = ["name"]
    ordering_fields = ["rating", "reviews_count", "name", "id"]


class ProductViewSet(StrictQueryParamsMixin, CachedListMixin, BaseReadOnlyViewSet):
    """Товары: список (фильтры/поиск/сортировка) и детали.

    * `select_related` — 1 запрос вместо N+1 на вложенные category/seller;
    * `defer` — в список не едут description/characteristics/images (~2/3 полезной нагрузки);
    * отдельный сериализатор для списка (см. AUDIT D-4).
    """

    basename_key = "products"
    queryset = Product.objects.select_related("category", "seller").all()
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    search_fields = ["title", "description"]
    ordering_fields = ["price", "rating", "reviews_count", "created_at", "old_price", "id"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        return ProductListSerializer if self.action == "list" else ProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = qs.defer("description", "characteristics", "images")
        return qs
