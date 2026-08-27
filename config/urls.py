from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from apps.products.views import ProductViewSet, CategoryViewSet, SellerViewSet

# Роутер для корня /api/ — категории и продукты без префикса /products/
router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'sellers', SellerViewSet, basename='seller')

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth: login, refresh, logout, register, me
    path("api/auth/", include("apps.users.auth_urls")),
    # Products + Categories + Sellers на корне /api/
    path("api/", include(router.urls)),
    # Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]