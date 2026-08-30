"""Сериализаторы заказов и кабинета продавца (§5.5, §5.6 ТЗ)."""

from rest_framework import serializers

from apps.core.datetime import iso_utc

from .models import Order, OrderItem


class OrderEventSerializer(serializers.Serializer):
    status = serializers.CharField()
    at = serializers.SerializerMethodField()
    note = serializers.CharField()

    def get_at(self, obj) -> str:
        return iso_utc(obj.at)


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["product_id", "title", "image", "price", "qty", "seller_id", "seller_name"]

    def get_product_id(self, obj):
        return obj.product_id

    def get_seller_name(self, obj):
        return obj.seller.name if obj.seller_id else ""


class ShopOrderSerializer(serializers.ModelSerializer):
    """Order из ТЗ: items — снимки позиций, timeline — события."""

    items = OrderItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    buyer_name = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "created_at",
            "subtotal",
            "discount",
            "promo_code",
            "delivery_cost",
            "total",
            "address",
            "pickup_point",
            "delivery_method",
            "payment_method",
            "comment",
            "items",
            "items_count",
            "buyer_name",
            "timeline",
        ]

    def get_created_at(self, obj) -> str:
        return iso_utc(obj.created_at)

    def get_items_count(self, obj) -> int:
        return sum(i.qty for i in obj.items.all())

    def get_buyer_name(self, obj) -> str:
        return obj.buyer_name

    def get_timeline(self, obj) -> list:
        return OrderEventSerializer(obj.events.all(), many=True).data


class SellerStatsSerializer(serializers.Serializer):
    product_count = serializers.IntegerField()
    draft_count = serializers.IntegerField()
    review_count = serializers.IntegerField()
    rating = serializers.FloatField()
    views = serializers.IntegerField()
    order_count = serializers.IntegerField()
    revenue = serializers.IntegerField()
    stock_units = serializers.IntegerField()
