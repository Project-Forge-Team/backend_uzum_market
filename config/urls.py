"""Маршруты API (§5 ТЗ). Все эндпоинты под /api/, плюс /products/gen/* и админка."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.views import DemoResetView, HealthView
from apps.products.gen_media import SeedMediaView

urlpatterns = [
    path("admin/", admin.site.urls),
    # --- auth (§5.1)
    path("api/auth/", include("apps.users.urls")),
    # --- каталог (§5.2–5.4)
    path("api/", include("apps.products.urls")),
    # --- заказы и кабинет продавца (§5.5–5.6)
    path("api/", include("apps.orders.urls")),
    # --- загрузка файлов (§5.7)
    path("api/", include("apps.uploads.urls")),
    # --- служебные (§5.7)
    path("api/health", HealthView.as_view(), name="health"),
    path("api/demo/reset/", DemoResetView.as_view(), name="demo-reset"),
    # --- демо-картинки сида: /products/gen/<file>.svg (§9 ТЗ)
    path("products/gen/<str:name>", SeedMediaView.as_view(), name="seed-media"),
    # --- OpenAPI + UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG or settings.SERVE_MEDIA:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
