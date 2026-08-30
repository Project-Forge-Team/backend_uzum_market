"""Сериализаторы каталога: ровно поля Product/Seller/Category/Review из §5 ТЗ."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.datetime import IsoDateTimeField

from .models import PRICE_MAX, STOCK_MAX, Category, Product, Review, Seller
from .translit import unique_slug


def rating_as_float(value):
    return float(value or 0)


class CategoryBriefSerializer(serializers.ModelSerializer):
    """Категория внутри карточки товара (§5.3): без color."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "emoji"]


class CategorySerializer(serializers.ModelSerializer):
    """Категория в /api/categories/: с color и product_count активных."""

    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "emoji", "color", "product_count"]


class SellerSerializer(serializers.ModelSerializer):
    """Seller из §5.2 ТЗ. product_count/order_count подкладываются контекстом/аннотацией."""

    rating = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    order_count = serializers.SerializerMethodField()
    created_at = IsoDateTimeField(read_only=True)

    class Meta:
        model = Seller
        fields = [
            "id",
            "name",
            "slug",
            "city",
            "description",
            "rating",
            "reviews_count",
            "product_count",
            "order_count",
            "verified",
            "owner_id",
            "created_at",
        ]

    def get_rating(self, obj) -> float:
        return rating_as_float(obj.rating)

    def _count(self, obj, key) -> int:
        # annotate на queryset либо карта в контексте (для встраивания в товары)
        counts = self.context.get("seller_counts")
        if counts is not None and obj.id in counts:
            return counts[obj.id].get(key, 0)
        return getattr(obj, key, 0) or 0

    def get_product_count(self, obj) -> int:
        return self._count(obj, "product_count")

    def get_order_count(self, obj) -> int:
        return self._count(obj, "order_count")


class ProductSerializer(serializers.ModelSerializer):
    """Product из §5.3 ТЗ — все поля обязательны для фронта."""

    old_price = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    monthly_payment = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    rating_breakdown = serializers.SerializerMethodField()
    delivery_time = serializers.CharField(read_only=True)
    stock = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    brand = serializers.CharField(read_only=True)
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    is_ad = serializers.BooleanField(read_only=True)
    views = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = IsoDateTimeField(read_only=True)
    updated_at = IsoDateTimeField(read_only=True)
    seller = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    has_own_review = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "price",
            "old_price",
            "discount_percent",
            "monthly_payment",
            "rating",
            "reviews_count",
            "rating_breakdown",
            "delivery_time",
            "stock",
            "in_stock",
            "brand",
            "image",
            "images",
            "characteristics",
            "is_ad",
            "views",
            "status",
            "created_at",
            "updated_at",
            "seller",
            "category",
            "has_own_review",
        ]

    def get_old_price(self, obj):
        # old_price имеет смысл только если больше price (§4 ТЗ)
        return obj.old_price if obj.old_price and obj.old_price > obj.price else None

    def get_monthly_payment(self, obj) -> dict:
        return obj.monthly_payment

    def get_rating(self, obj) -> float:
        return rating_as_float(obj.rating)

    def get_rating_breakdown(self, obj) -> list:
        return obj.rating_breakdown or [{"stars": stars, "count": 0} for stars in (5, 4, 3, 2, 1)]

    def get_image(self, obj) -> str:
        images = obj.images or []
        return images[0] if images else ""

    def get_images(self, obj) -> list:
        return obj.images or []

    def get_characteristics(self, obj) -> dict:
        return obj.characteristics or {}

    def get_seller(self, obj):
        return SellerSerializer(
            obj.seller, context={**self.context, "seller_counts": self.context.get("seller_counts")}
        ).data

    def get_category(self, obj):
        return CategoryBriefSerializer(obj.category).data if obj.category else None

    def get_has_own_review(self, obj) -> bool:
        reviewed = self.context.get("reviewed_product_ids")
        if reviewed is None:
            user = self.context.get("request").user if self.context.get("request") else None
            if user is None or not getattr(user, "is_authenticated", False):
                return False
            reviewed = set(
                Review.objects.filter(user=user, product_id__in=[obj.pk]).values_list("product_id", flat=True)
            )
        return obj.pk in reviewed


class ReviewSerializer(serializers.ModelSerializer):
    initials = serializers.CharField(read_only=True)
    own = serializers.SerializerMethodField()
    created_at = IsoDateTimeField(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "product_id",
            "author",
            "initials",
            "rating",
            "text",
            "pros",
            "cons",
            "created_at",
            "verified",
            "seller_reply",
            "own",
        ]

    def get_own(self, obj) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and obj.user_id == user.pk)


class ProductWriteSerializer(serializers.ModelSerializer):
    """POST/PATCH /products/: частичный payload, валидируем слитые значения (§4 ТЗ)."""

    category_id = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), source="category", required=False)
    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.all(), required=False, write_only=True
    )
    images = serializers.ListField(child=serializers.CharField(max_length=500), required=False, max_length=8)
    characteristics = serializers.DictField(
        child=serializers.CharField(max_length=200, allow_blank=True), required=False
    )

    class Meta:
        model = Product
        fields = [
            "title",
            "description",
            "price",
            "old_price",
            "stock",
            "brand",
            "delivery_time",
            "category_id",
            "category",
            "images",
            "characteristics",
            "status",
            "is_ad",
        ]
        extra_kwargs = {
            "title": {"max_length": 120},
            "brand": {"max_length": 40, "required": False},
            "delivery_time": {"max_length": 40, "required": False},
            "status": {"required": False},
        }

    # --- валидации §4 ТЗ -----------------------------------------------------

    def validate_title(self, value):
        value = (value or "").strip()
        if not (8 <= len(value) <= 120):
            raise serializers.ValidationError("Название должно быть от 8 до 120 символов.")
        return value

    def validate_description(self, value):
        value = (value or "").strip()
        if not (20 <= len(value) <= 4000):
            raise serializers.ValidationError("Описание должно быть от 20 до 4000 символов.")
        return value

    def validate_price(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Цена должна быть целым числом больше нуля.")
        if value > PRICE_MAX:
            raise serializers.ValidationError(f"Цена не может превышать {PRICE_MAX}.")
        return value

    def validate_stock(self, value):
        if value is None or not (0 <= value <= STOCK_MAX):
            raise serializers.ValidationError(f"Остаток должен быть целым числом от 0 до {STOCK_MAX}.")
        return value

    def validate_characteristics(self, value):
        if value is None:
            return value
        if len(value) > 24:
            raise serializers.ValidationError("Не больше 24 характеристик.")
        return {str(k)[:100]: v for k, v in value.items()}

    def validate(self, attrs):
        # PATCH: валидируем СЛИТЫЕ значения (не пришедшие поля не трогаем).
        instance = self.instance
        price = attrs.get("price", getattr(instance, "price", None))
        old_price = attrs.get("old_price", getattr(instance, "old_price", None))
        if old_price is not None and old_price <= 0:
            raise serializers.ValidationError({"old_price": "Старая цена должна быть больше нуля."})
        if old_price is not None and price is not None and old_price <= price:
            # скидки нет — старую цену не храним (§4: «иначе отдавать null»)
            attrs["old_price"] = None
        return attrs

    def create(self, validated_data):
        seller = validated_data.pop("seller")
        category = validated_data.pop("category", None)
        if category is None:
            raise serializers.ValidationError({"category_id": "Категория обязательна."})
        slug = unique_slug(Product, validated_data["title"], max_length=140)
        try:
            return Product.objects.create(seller=seller, category=category, slug=slug, **validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        try:
            instance.save()
        except DjangoValidationError as exc:
            field = next(iter(exc.message_dict or {}), None)
            msg = exc.messages[0]
            raise serializers.ValidationError({field or "__all__": msg} if field else msg) from exc
        return instance
