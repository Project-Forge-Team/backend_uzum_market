"""Маршруты каталога. Единственный источник правды — config/urls.py его подключает.

Раньше router был продублирован и в config/urls.py, и здесь (второй не использовался).
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, SellerViewSet

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"sellers", SellerViewSet, basename="seller")

urlpatterns = [
    path("", include(router.urls)),
]
