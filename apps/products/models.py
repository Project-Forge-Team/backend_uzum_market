from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    # Индекс по created_at задан в Meta.indexes (product_created_idx) — db_index здесь не нужен.
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


# 1. Отдельная модель Продавца
class Seller(models.Model):
    name = models.CharField(max_length=255)
    rating = models.DecimalField(
        default=0.0,
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Средняя оценка 0.00–5.00",
    )
    reviews_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-rating"]
        verbose_name = "Продавец"
        verbose_name_plural = "Продавцы"
        constraints = [
            models.CheckConstraint(condition=models.Q(rating__lte=5), name="seller_rating_max_5"),
        ]

    def __str__(self):
        return self.name


# 2. Отдельная модель Категории
class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        indexes = [models.Index(fields=["name"], name="category_name_idx")]

    def __str__(self):
        return self.name


# 3. Основная модель Товара (ссылается на остальные)
class Product(TimeStampedModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Цена в копейках/тиынах — как отдаёт Uzum (целое число со 2 знаками).",
    )
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    rating = models.DecimalField(
        default=0.0,
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="float давал 4.8499999… в JSON, поэтому Decimal(3,2)",
    )
    reviews_count = models.PositiveIntegerField(default=0)
    monthly_payment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    delivery_time = models.CharField(max_length=100)
    # URL на CDN/medиа: ImageField ломал внешние ссылки (см. AUDIT B-1) и требовал файл на диске.
    image = models.URLField(max_length=500, blank=True)
    images = models.JSONField(default=list, help_text='Список строк-URL, например ["https://cdn/1.jpg"]')
    characteristics = models.JSONField(default=dict, help_text="Объект «название → значение»")
    is_ad = models.BooleanField(default=False)

    # Связи с другими моделями
    seller = models.ForeignKey(
        Seller,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        related_query_name="product",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        related_query_name="product",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        indexes = [
            # список каталога всегда сортируется по created_at DESC: без индекса
            # БД делала SCAN + сортировку в temp B-tree (12.3 мс → 2.7 мс на 20k строк)
            models.Index(fields=["-created_at"], name="product_created_idx"),
            models.Index(fields=["category", "-created_at"], name="product_cat_created_idx"),
            models.Index(fields=["seller", "-created_at"], name="product_sel_created_idx"),
            models.Index(fields=["price"], name="product_price_idx"),
            models.Index(fields=["is_ad"], name="product_isad_idx"),
        ]
        # Только те ограничения, нарушение которых = испорченные данные.
        # «old_price >= price» сознательно НЕ в БД: на существующей базе такое может
        # встречаться (ошибочный импорт), и миграция с CheckConstraint тогда упадёт.
        # Правило проверяется на уровне сериализатора/формы.
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(condition=models.Q(rating__gte=0), name="product_rating_non_negative"),
            models.CheckConstraint(condition=models.Q(rating__lte=5), name="product_rating_max_5"),
        ]

    def __str__(self):
        return self.title

    @property
    def discount_percent(self):
        """Скидка считается на бэке: иначе у фронта и каталога разные цифры на глаз."""
        if not self.old_price or self.old_price <= self.price:
            return 0
        return round(float((self.old_price - self.price) / self.old_price * 100))
