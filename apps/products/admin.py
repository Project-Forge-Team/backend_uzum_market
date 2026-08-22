from django.contrib import admin
from .models import Product, Category, Seller

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug')

@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'rating')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'price', 'category', 'seller', 'is_ad')
    list_filter = ('category', 'is_ad')
    search_fields = ('title', 'description')