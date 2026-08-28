from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Category, Product, Seller


def absolute_media_url(value, request):
    """Внешний URL (https://cdn/…) отдаём как есть, локальный путь — с доменом запроса.

    Раньше `image` был ImageField, и DRF заворачивал ЛЮБОЕ значение в MEDIA_URL,
    превращая https-ссылку в битый /media/https%3A/… (см. AUDIT B-1).
    """
    if not value:
        return None
    value = str(value)
    if value.startswith(("http://", "https://", "//", "/")):
        return value
    base = settings.MEDIA_URL  # всегда с ведущим и завершающим '/' (см. settings._url_prefix)
    path = f"{base}{value.lstrip('/')}"
    return request.build_absolute_uri(path) if request is not None else path


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class SellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seller
        fields = ["id", "name", "rating", "reviews_count"]


class _ImageSerializerMixin(serializers.Serializer):
    image = serializers.SerializerMethodField(help_text="Главное изображение (абсолютный URL)")

    @extend_schema_field(serializers.URLField(max_length=500, allow_null=True))
    def get_image(self, obj):
        return absolute_media_url(obj.image, self.context.get("request"))


class ProductListSerializer(_ImageSerializerMixin, serializers.ModelSerializer):
    """Компактная карточка для сетки каталога.

    Полный сериализатор на 10 товаров ≈ 15 КБ (description + characteristics + вложенный
    seller), а в сетке эти поля не используются — список уезжает в ~3 раза меньше.
    """

    category = CategorySerializer(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "price",
            "old_price",
            "discount_percent",
            "rating",
            "reviews_count",
            "monthly_payment",
            "delivery_time",
            "image",
            "is_ad",
            "category",
            "created_at",
        ]
        read_only_fields = fields


class ProductSerializer(_ImageSerializerMixin, serializers.ModelSerializer):
    """Полная карточка товара (retrieve)."""

    seller = SellerSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    images = serializers.ListField(
        child=serializers.URLField(max_length=500),
        required=False,
        help_text="Дополнительные изображения",
    )
    characteristics = serializers.DictField(
        child=serializers.CharField(max_length=500),
        required=False,
        help_text="Характеристики вида «название → значение»",
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "price",
            "old_price",
            "discount_percent",
            "rating",
            "reviews_count",
            "monthly_payment",
            "delivery_time",
            "image",
            "images",
            "characteristics",
            "is_ad",
            "category",
            "seller",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if isinstance(data.get("images"), list):
            # в БД могут лежать относительные пути (см. исторический seed) — нормализуем к URL
            data["images"] = [absolute_media_url(item, request) for item in data["images"] if item]
        if isinstance(data.get("characteristics"), dict):
            data["characteristics"] = {str(k): str(v) for k, v in data["characteristics"].items()}
        else:
            data["characteristics"] = {}
        return data
