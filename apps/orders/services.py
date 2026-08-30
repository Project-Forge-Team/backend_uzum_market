"""Бизнес-логика заказов (§4, §6 ТЗ): суммы, промокод, атомарное списание, статусы."""

import random

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.products.models import Product

from .models import (
    ADVANCE_TRANSITIONS,
    DELIVERY_COST,
    FREE_DELIVERY_FROM,
    MAX_ITEMS,
    MAX_QTY,
    STATUS_NOTES,
    Order,
    OrderEvent,
    OrderItem,
    PromoCode,
)


class OrderError(ValidationError):
    """400 с detail для пользователя (тексты из ТЗ)."""


def find_promo(code: str, subtotal: int):
    """Активный промокод, подходящий по min_subtotal. Иначе None."""
    code = (code or "").strip().upper()
    if not code:
        return None
    try:
        promo = PromoCode.objects.get(code=code)
    except PromoCode.DoesNotExist:
        return None
    if not promo.active:
        return None
    if promo.valid_to is not None and promo.valid_to < timezone.now():
        return None
    if subtotal < promo.min_subtotal:
        return None
    return promo


def calc_totals(subtotal: int, delivery_method: str, promo_code: str | None):
    """Единый расчёт сумм для превью и оформления (§4 ТЗ)."""
    promo = find_promo(promo_code, subtotal)
    discount = round(subtotal * promo.percent / 100) if promo else 0
    if delivery_method == Order.DeliveryMethod.PICKUP:
        delivery_cost = 0
    else:
        delivery_cost = 0 if (subtotal - discount) >= FREE_DELIVERY_FROM else DELIVERY_COST
    total = subtotal - discount + delivery_cost
    return {
        "discount": discount,
        "delivery_cost": delivery_cost,
        "total": total,
        "promo_valid": promo is not None,
        "promo_label": promo.label if promo else "",
    }


def generate_number() -> str:
    for _ in range(20):
        number = f"UZ-{random.randint(0, 999999):06d}"  # noqa: S311 — демо-проект
        if not Order.objects.filter(number=number).exists():
            return number
    raise APIException("Не удалось сгенерировать номер заказа, попробуйте ещё раз.")


def validate_address_fields(delivery_method: str, address: str, pickup_point: str):
    if delivery_method not in Order.DeliveryMethod.values:
        raise OrderError({"delivery_method": "Способ доставки: courier или pickup."})
    if delivery_method == Order.DeliveryMethod.COURIER and len((address or "").strip()) < 8:
        raise OrderError({"address": "Укажите адрес доставки (минимум 8 символов)."})
    if delivery_method == Order.DeliveryMethod.PICKUP and not (pickup_point or "").strip():
        raise OrderError({"pickup_point": "Укажите пункт самовывоза."})


@transaction.atomic
def create_order(
    user,
    items: list[dict],
    delivery_method: str,
    payment_method: str,
    address: str = "",
    pickup_point: str = "",
    comment: str = "",
    promo_code: str | None = None,
) -> Order:
    """Оформление заказа: суммы считает сервер, остатки списываются атомарно (§6.1 ТЗ).

    `items`: [{product_id, qty}] — количества сливаются при дублях, остаток
    проверяется и списывается под блокировкой SELECT … FOR UPDATE.
    """
    if not isinstance(items, list) or not (1 <= len(items) <= MAX_ITEMS):
        raise OrderError({"items": f"В заказе должно быть от 1 до {MAX_ITEMS} позиций."})

    merged: dict[int, int] = {}
    for item in items:
        try:
            product_id = int(item.get("product_id"))
            qty = int(item.get("qty"))
        except (TypeError, ValueError):
            raise OrderError({"items": "Каждая позиция: product_id и qty — целые числа."}) from None
        if not (1 <= qty <= MAX_QTY):
            raise OrderError({"items": f"Количество каждой позиции — от 1 до {MAX_QTY}."})
        merged[product_id] = merged.get(product_id, 0) + qty
    if len(merged) > MAX_ITEMS:
        raise OrderError({"items": f"В заказе должно быть от 1 до {MAX_ITEMS} позиций."})

    if payment_method not in Order.PaymentMethod.values:
        raise OrderError({"payment_method": "Способ оплаты: card, cash или installment."})
    validate_address_fields(delivery_method, address, pickup_point)

    # Блокируем строки товаров: параллельные заказы не перепродают один остаток.
    product_ids = list(merged)
    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(id__in=product_ids, status=Product.Status.ACTIVE)
        .select_related("seller")
    }
    for product_id in product_ids:
        if product_id not in products:
            raise OrderError({"items": f"Товар {product_id} не найден или недоступен."})

    subtotal = 0
    for product_id, qty in merged.items():
        product = products[product_id]
        if product.stock < qty:
            raise OrderError(f"«{product.title}»: на складе всего {product.stock} шт.")
        subtotal += int(product.price) * qty

    totals = calc_totals(subtotal, delivery_method, promo_code)
    order = Order.objects.create(
        number=generate_number(),
        user=user,
        status=Order.Status.NEW,
        subtotal=subtotal,
        discount=totals["discount"],
        promo_code=(promo_code or "").strip().upper() or None if totals["promo_valid"] else None,
        delivery_cost=totals["delivery_cost"],
        total=totals["total"],
        address=(address or "").strip(),
        pickup_point=(pickup_point or "").strip(),
        delivery_method=delivery_method,
        payment_method=payment_method,
        comment=(comment or "").strip(),
    )
    for product_id, qty in merged.items():
        product = products[product_id]
        Product.objects.filter(pk=product_id).update(stock=F("stock") - qty)
        OrderItem.objects.create(
            order=order,
            product=product,
            title=product.title,
            image=product.image,
            price=product.price,
            qty=qty,
            seller=product.seller,
        )
    OrderEvent.objects.create(order=order, status=Order.Status.NEW, note=STATUS_NOTES[Order.Status.NEW])
    return order


def can_advance(status: str) -> bool:
    return status in ADVANCE_TRANSITIONS


def next_status(status: str) -> str:
    return ADVANCE_TRANSITIONS[status]


@transaction.atomic
def advance_order(order: Order) -> Order:
    if order.status == Order.Status.DELIVERED:
        raise OrderError("Заказ уже доставлен: статус менять некуда.")
    if order.status == Order.Status.CANCELLED:
        raise OrderError("Заказ отменён — статус поменять нельзя.")
    if not can_advance(order.status):
        raise OrderError("Статус заказа изменить нельзя.")
    order.status = next_status(order.status)
    order.save(update_fields=["status", "updated_at"])
    OrderEvent.objects.create(order=order, status=order.status, note=STATUS_NOTES[order.status])
    return order


@transaction.atomic
def cancel_order(order: Order) -> Order:
    """Отмена доступна только покупателю; остатки возвращаются (§6.2 ТЗ)."""
    if order.status in (Order.Status.DELIVERED, Order.Status.CANCELLED):
        raise OrderError(f"Заказ со статусом «{order.get_status_display()}» отменить нельзя.")
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    for item in order.items.select_related("product"):
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.qty)
    OrderEvent.objects.create(order=order, status=order.status, note=STATUS_NOTES[order.status])
    return order


def purchased_qty_map(user, product_ids: list[int]) -> dict[int, int]:
    """product_id → сколько штук куплено пользователем в не-отменённых заказах (§5.4 ТЗ)."""
    if user is None or not getattr(user, "is_authenticated", False) or not product_ids:
        return {}
    rows = (
        OrderItem.objects.filter(order__user=user, product_id__in=product_ids)
        .exclude(order__status=Order.Status.CANCELLED)
        .values("product_id")
        .annotate(qty=Sum("qty"))
    )
    return {row["product_id"]: row["qty"] for row in rows}
