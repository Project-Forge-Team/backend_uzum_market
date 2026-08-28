from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth: register, login, refresh, logout, csrf, me
    path("api/auth/", include("apps.users.urls")),
    # Каталог: products / categories / sellers (роутер объявлен один раз — в apps.products.urls)
    path("api/", include("apps.products.urls")),
    # OpenAPI + UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG or settings.SERVE_MEDIA:
    from django.conf.urls.static import static

    # Без этого /media/ отдавало 404 даже локально (WhiteNoise обслуживает только статику).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
