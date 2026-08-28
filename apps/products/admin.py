from django.contrib import admin

from .models import Category, Product, Seller


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "products_count")
    list_display_links = ("name",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50

    @admin.display(description="Товаров")
    def products_count(self, obj):
        return obj.products_total  # из annotate() — иначе N+1 на каждую строку списка

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(products_total=Count("products", distinct=True))


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rating", "reviews_count")
    list_display_links = ("name",)
    search_fields = ("name",)
    ordering = ("-rating",)
    list_per_page = 50


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "price", "old_price", "rating", "category", "seller", "is_ad", "created_at")
    # Без list_select_related list_display по category/seller = 21 запрос на страницу
    # вместо 1 (замерено на 20 000 товаров).
    list_select_related = ("category", "seller")
    list_filter = ("category", "is_ad", "seller")
    search_fields = ("title", "description")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    autocomplete_fields = ()
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "description", "is_ad")}),
        ("Цены", {"fields": ("price", "old_price", "monthly_payment")}),
        ("Медиа", {"fields": ("image", "images", "characteristics")}),
        ("Продавец и категория", {"fields": ("seller", "category", "delivery_time")}),
        ("Рейтинг", {"fields": ("rating", "reviews_count")}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )
