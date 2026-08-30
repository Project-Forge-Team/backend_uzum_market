"""Заказы (§2, §4 ТЗ): snapshot-позиции, append-only таймлайн, промокоды."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.products.models import TimeStampedModel

FREE_DELIVERY_FROM = 500_000
DELIVERY_COST = 25_000
MAX_ITEMS = 30
MAX_QTY = 20


class PromoCode(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True)
    percent = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    min_subtotal = models.BigIntegerField(default=0)
    label = models.CharField(max_length=120, blank=True, default="")
    active = models.BooleanField(default=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PACKING = "packing", "Сборка"
        SHIPPING = "shipping", "В доставке"
        DELIVERED = "delivered", "Доставлен"
        CANCELLED = "cancelled", "Отменён"

    class DeliveryMethod(models.TextChoices):
        COURIER = "courier", "Курьер"
        PICKUP = "pickup", "Самовывоз"

    class PaymentMethod(models.TextChoices):
        CARD = "card", "Карта"
        CASH = "cash", "Наличные"
        INSTALLMENT = "installment", "Рассрочка"

    number = models.CharField(max_length=16, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="orders")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    subtotal = models.BigIntegerField(default=0, editable=False)
    discount = models.BigIntegerField(default=0, editable=False)
    promo_code = models.CharField(max_length=32, null=True, blank=True)
    delivery_cost = models.BigIntegerField(default=0, editable=False)
    total = models.BigIntegerField(default=0, editable=False)
    address = models.CharField(max_length=250, blank=True, default="")
    pickup_point = models.CharField(max_length=120, blank=True, default="")
    delivery_method = models.CharField(max_length=10, choices=DeliveryMethod.choices, default=DeliveryMethod.COURIER)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CARD)
    comment = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"], name="order_user_created_idx")]

    def __str__(self):
        return self.number

    @property
    def items_count(self) -> int:
        return sum(item.qty for item in self.items.all())

    @property
    def buyer_name(self) -> str:
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email


STATUS_NOTES = {
    Order.Status.NEW: "Заказ оформлен",
    Order.Status.PACKING: "Заказ собирается",
    Order.Status.SHIPPING: "Заказ собран и передан в доставку",
    Order.Status.DELIVERED: "Заказ доставлен",
    Order.Status.CANCELLED: "Заказ отменён, товары возвращены на склад",
}

# Разрешённые переходы статус-машины (§4 ТЗ).
ADVANCE_TRANSITIONS = {
    Order.Status.NEW: Order.Status.PACKING,
    Order.Status.PACKING: Order.Status.SHIPPING,
    Order.Status.SHIPPING: Order.Status.DELIVERED,
}


class OrderItem(models.Model):
    """Снимок позиции: цена/название/картинка копируются на момент заказа (§2 ТЗ)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    title = models.CharField(max_length=140)
    image = models.CharField(max_length=500, blank=True, default="")
    price = models.BigIntegerField()
    qty = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    seller = models.ForeignKey("products.Seller", on_delete=models.CASCADE, related_name="order_items")

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"
        indexes = [
            models.Index(fields=["order"], name="orderitem_order_idx"),
            models.Index(fields=["seller"], name="orderitem_seller_idx"),
        ]

    def __str__(self):
        return f"{self.title} ×{self.qty}"


class OrderEvent(models.Model):
    """Append-only таймлайн: только вставка (§2 ТЗ)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=12, choices=Order.Status.choices)
    at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        verbose_name = "Событие заказа"
        verbose_name_plural = "События заказов"
        ordering = ["at", "id"]
        indexes = [models.Index(fields=["order", "at"], name="orderevent_order_idx")]

    def __str__(self):
        return f"{self.order_id}:{self.status}"
