from django.urls import path

from .auth_views import CookieTokenObtainPairView, CookieTokenRefreshView, CookieTokenLogoutView
from .views import MeView, RegisterView

urlpatterns = [
    path("login/", CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", CookieTokenLogoutView.as_view(), name="token_logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
]
