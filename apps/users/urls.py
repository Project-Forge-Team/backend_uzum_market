from django.urls import path

from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CustomTokenVerifyView,
    MeView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='refresh'),
    path('verify/', CustomTokenVerifyView.as_view(), name='verify'),
    path('me/', MeView.as_view(), name='me'),
]
