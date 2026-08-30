from django.contrib import admin

from .models import Category, Product, Review, Seller


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ["author", "rating", "text", "verified", "seller_reply", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["emoji", "name", "slug", "color"]
    list_display_links = ["name"]
    search_fields = ["name", "slug"]
    list_per_page = 50


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "city", "owner", "rating", "reviews_count", "verified"]
    list_display_links = ["name"]
    search_fields = ["name", "slug", "city"]
    list_filter = ["verified", "city"]
    list_select_related = ["owner"]
    list_per_page = 50


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["title", "seller", "category", "price", "stock", "status", "is_ad", "views", "rating"]
    list_display_links = ["title"]
    list_filter = ["status", "is_ad", "category"]
    search_fields = ["title", "brand", "slug"]
    list_select_related = ["seller", "category"]
    date_hierarchy = "created_at"
    list_per_page = 50
    inlines = [ReviewInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["author", "product", "rating", "verified", "seller_reply", "created_at"]
    list_select_related = ["product"]
    search_fields = ["author", "text"]
    list_filter = ["rating", "verified"]
    date_hierarchy = "created_at"
    list_per_page = 50
