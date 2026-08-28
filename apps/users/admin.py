from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Админка для кастомной модели User (email-логин)."""

    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "phone", "is_staff", "is_active", "date_joined"]
    list_display_links = ["email"]
    list_filter = ["is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    date_hierarchy = "date_joined"
    list_per_page = 50
    autocomplete_fields = []

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Личная информация", {"fields": ("first_name", "last_name", "phone")}),
        ("Права", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "first_name", "last_name", "phone"),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")
