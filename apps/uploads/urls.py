"""Маршруты загрузок (§5.7 ТЗ)."""

from django.urls import path

from .views import UploadFileView, UploadView

urlpatterns = [
    path("uploads/", UploadView.as_view(), name="uploads"),
    path("uploads/<str:key>", UploadFileView.as_view(), name="upload-file"),
]
