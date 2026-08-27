from django.urls import path

from .auth_views import CookieTokenObtainPairView, CookieTokenRefreshView, CookieTokenLogoutView

urlpatterns = [
    path("login/", CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", CookieTokenLogoutView.as_view(), name="token_logout"),
]
