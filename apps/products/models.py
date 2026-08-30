"""Модели каталога (§2 ТЗ): категории, магазины, товары, отзывы.

Деньги — целые числа сумов (никаких дробей и строк). Рейтинг товара/магазина
денормализуется при записи отзывов (§8 ТЗ), чтобы список из 120 карточек не
делал N+1 агрегатов.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

PRICE_MAX = 5_000_000_000
STOCK_MAX = 99_999


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class Category(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=60, unique=True)
    emoji = models.CharField(max_length=8, default="🛍️")
    color = models.CharField(max_length=9, default="#F5F5F5", help_text="HEX-цвет чипа, например #EDE9FF")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]
        indexes = [models.Index(fields=["slug"], name="category_slug_idx")]

    def __str__(self):
        return f"{self.emoji} {self.name}"


class Seller(models.Model):
    """Магазин. slug стабилен и не меняется при переименовании (§4 ТЗ)."""

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=80, unique=True)
    city = models.CharField(max_length=40, default="Ташкент")
    description = models.CharField(max_length=600, blank=True, default="")
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shop",
        verbose_name="Владелец",
    )
    verified = models.BooleanField(default=False, verbose_name="Документы проверены")
    rating = models.DecimalField(default=0, max_digits=3, decimal_places=2, editable=False)
    reviews_count = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Магазины"
        indexes = [models.Index(fields=["-rating"], name="seller_rating_idx")]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активный"
        DRAFT = "draft", "Черновик"
        ARCHIVED = "archived", "В архиве"

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, default="")
    price = models.BigIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(PRICE_MAX)],
        help_text="Цена в сумах, целое число",
    )
    old_price = models.BigIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(PRICE_MAX)]
    )
    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(STOCK_MAX)])
    brand = models.CharField(max_length=40, blank=True, default="Без бренда")
    delivery_time = models.CharField(max_length=40, blank=True, default="1–2 дня")
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, related_name="products")
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="products")
    is_ad = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    views = models.PositiveIntegerField(default=0)
    # Проще (§2 ТЗ): изображения и характеристики — JSON. Фронт ждёт ровно это.
    images = models.JSONField(default=list, blank=True, help_text="Массив URL, ≤ 8; индекс 0 — главное")
    characteristics = models.JSONField(default=dict, blank=True, help_text="Объект «название → значение», ≤ 24 пар")
    # Денормализованные агрегаты отзывов (§8 ТЗ).
    rating = models.DecimalField(default=0, max_digits=3, decimal_places=2, editable=False)
    reviews_count = models.PositiveIntegerField(default=0, editable=False)
    rating_breakdown = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "category_id"], name="product_status_cat_idx"),
            models.Index(fields=["seller", "status"], name="product_seller_status_idx"),
            models.Index(fields=["price"], name="product_price_idx"),
            models.Index(fields=["-created_at"], name="product_created_idx"),
            models.Index(fields=["-views"], name="product_views_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=1), name="product_price_positive"),
            models.CheckConstraint(condition=models.Q(rating__gte=0, rating__lte=5), name="product_rating_0_5"),
        ]

    def __str__(self):
        return self.title

    # --- вычисляемые поля контракта -----------------------------------------

    @property
    def discount_percent(self) -> int:
        if not self.old_price or self.old_price <= self.price:
            return 0
        return round((self.old_price - self.price) / self.old_price * 100)

    @property
    def monthly_payment(self) -> dict:
        per_month = -(-self.price // 12 // 100) * 100  # ceil(price/12/100)*100 без float
        return {"months": 12, "per_month": per_month, "overpay": 0}

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def image(self) -> str:
        return self.images[0] if self.images else ""


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="reviews"
    )
    # Денормализованное имя автора на момент написания (§2 ТЗ); user может быть null у сидовых отзывов.
    author = models.CharField(max_length=80)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField()
    pros = models.CharField(max_length=200, blank=True, default="")
    cons = models.CharField(max_length=200, blank=True, default="")
    verified = models.BooleanField(default=False, help_text="Есть не-отменённый заказ с этим товаром")
    seller_reply = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["product", "-created_at"], name="review_product_created_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="review_unique_per_user_product",
                condition=models.Q(user__isnull=False),
            ),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_5"),
        ]

    def __str__(self):
        return f"{self.author} → {self.product_id}"

    @property
    def initials(self) -> str:
        return (self.author or "?").strip()[:1].upper()
