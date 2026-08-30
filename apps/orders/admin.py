from django.contrib import admin

from .models import Order, OrderEvent, OrderItem, PromoCode


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ["title", "product", "price", "qty", "seller"]
    readonly_fields = fields


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    fields = ["status", "at", "note"]
    readonly_fields = fields


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "user", "status", "total", "items_count", "created_at"]
    list_display_links = ["number"]
    list_filter = ["status", "delivery_method", "payment_method"]
    search_fields = ["number", "user__email"]
    list_select_related = ["user"]
    date_hierarchy = "created_at"
    list_per_page = 50
    inlines = [OrderItemInline, OrderEventInline]

    @admin.display(description="Позиций")
    def items_count(self, obj):
        return obj.items.count()


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "percent", "min_subtotal", "active", "valid_to", "label"]
    list_filter = ["active"]
