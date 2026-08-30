from django.contrib import admin

from .models import MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ["key", "filename", "owner", "content_type", "size", "created_at"]
    list_select_related = ["owner"]
    search_fields = ["key", "filename"]
    list_filter = ["content_type"]
    date_hierarchy = "created_at"
    list_per_page = 50
