from django.urls import path

from .auth_views import (
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    PasswordView,
    RegisterView,
)

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("password/", PasswordView.as_view(), name="password"),
]
