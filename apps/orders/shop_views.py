"""Кабинет продавца (§5.6 ТЗ): /shop/, /shop/orders/ + статистика."""

from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cache_private
from apps.core.pagination import EnvelopePagination
from apps.products.models import Product, Review, Seller
from apps.products.serializers import SellerSerializer
from apps.products.services import ShopCreationError, create_seller

from .models import Order, OrderItem
from .serializers import ShopOrderSerializer


class ShopView(APIView):
    """GET /shop/ — Seller или null; POST /shop/ — создать (идемпотентно); PATCH — обновить."""

    serializer_class = serializers.Serializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["shop"], responses={200: None})
    def get(self, request):
        shop = getattr(request.user, "shop", None)
        if shop is None:
            # по ТЗ: 200 с телом null (не 404)
            from django.http import HttpResponse

            return cache_private(HttpResponse("null", content_type="application/json"), request)
        from django.db.models import Count, Q

        from apps.orders.models import Order

        shop = (
            Seller.objects.annotate(
                product_count=Count("products", filter=Q(products__status=Product.Status.ACTIVE), distinct=True),
                order_count=Count(
                    "order_items__order",
                    filter=~Q(order_items__order__status=Order.Status.CANCELLED),
                    distinct=True,
                ),
            )
            .select_related("owner")
            .get(pk=shop.pk)
        )
        data = SellerSerializer(shop, context={"request": request}).data
        return cache_private(Response(data), request)

    @extend_schema(tags=["shop"], responses={201: None})
    def post(self, request):
        name = (request.data.get("name") or "").strip() if isinstance(request.data, dict) else ""
        existing = getattr(request.user, "shop", None)
        if existing is not None:
            # Идемпотентность (§4 ТЗ): магазин уже есть — не дублируем.
            return Response({"id": existing.pk, "detail": "Магазин уже существует"})
        try:
            shop = create_seller(owner=request.user, name=name)
        except ShopCreationError as exc:
            return Response(
                {"detail": str(exc), "fields": {exc.field: str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"id": shop.pk, "detail": "Магазин создан"}, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["shop"], responses={200: None, 404: None})
    def patch(self, request):
        shop = getattr(request.user, "shop", None)
        if shop is None:
            return Response({"detail": "У вас пока нет магазина"}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}

        name = (data.get("name") or "").strip()
        if name:
            if not (3 <= len(name) <= 60):
                return Response(
                    {
                        "detail": "Название магазина должно быть от 3 до 60 символов.",
                        "fields": {"name": "Название магазина должно быть от 3 до 60 символов."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shop.name = name  # slug стабилен и не меняется (§4 ТЗ)
        if "description" in data:
            description = (data.get("description") or "").strip()
            if len(description) > 600:
                return Response(
                    {"detail": "Описание — до 600 символов.", "fields": {"description": "Описание — до 600 символов."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shop.description = description
        if "city" in data:
            city = (data.get("city") or "").strip()
            if not city or len(city) > 40:
                return Response(
                    {"detail": "Город — до 40 символов.", "fields": {"city": "Город — до 40 символов."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shop.city = city
        shop.save()
        return Response({"id": shop.pk, "detail": "Данные сохранены"})


class ShopOrdersView(APIView):
    """GET /shop/orders/ — заказы магазина: только свои позиции + SellerStats (§5.6 ТЗ)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["shop"], responses={200: None})
    def get(self, request):
        shop = getattr(request.user, "shop", None)
        if shop is None:
            envelope = EnvelopePagination.whole_list([])
            envelope["stats"] = {
                "product_count": 0,
                "draft_count": 0,
                "review_count": 0,
                "rating": 0.0,
                "views": 0,
                "order_count": 0,
                "revenue": 0,
                "stock_units": 0,
            }
            return cache_private(Response(envelope), request)

        items = (
            OrderItem.objects.filter(seller=shop)
            .select_related("order", "order__user")
            .prefetch_related("order__items__seller", "order__events")
            .order_by("-order__created_at", "-order__id")
        )
        orders = []
        seen: set[int] = set()
        for item in items:
            order = item.order
            if order.pk in seen:
                continue
            seen.add(order.pk)
            # В выдаче магазина — только позиции этого продавца, суммы по ним (§5.6 ТЗ).
            own_items = [i for i in order.items.all() if i.seller_id == shop.pk]
            subtotal = sum(int(i.price) * i.qty for i in own_items)
            serialized = ShopOrderSerializer(order, context={"request": request}).data
            serialized.update(
                {
                    "items": [
                        {
                            "product_id": i.product_id,
                            "title": i.title,
                            "image": i.image,
                            "price": i.price,
                            "qty": i.qty,
                            "seller_id": i.seller_id,
                            "seller_name": i.seller.name,
                        }
                        for i in own_items
                    ],
                    "items_count": sum(i.qty for i in own_items),
                    "subtotal": subtotal,
                    "discount": 0,
                    "promo_code": None,
                    "delivery_cost": 0,
                    "total": subtotal,
                }
            )
            orders.append(serialized)

        envelope = EnvelopePagination.whole_list(orders)
        envelope["stats"] = seller_stats(shop)
        return cache_private(Response(envelope), request)


def seller_stats(shop) -> dict:
    products = Product.objects.filter(seller=shop)
    active = products.filter(status=Product.Status.ACTIVE)
    live_items = OrderItem.objects.filter(seller=shop).exclude(order__status=Order.Status.CANCELLED)
    revenue = live_items.aggregate(v=Coalesce(Sum(F("price") * F("qty")), 0))["v"]
    order_count = live_items.values("order").distinct().count()
    review_count = Review.objects.filter(product__seller=shop).count()
    views = products.aggregate(v=Coalesce(Sum("views"), 0))["v"]
    stock_units = products.aggregate(v=Coalesce(Sum("stock"), 0))["v"]
    return {
        "product_count": active.count(),
        "draft_count": products.filter(status=Product.Status.DRAFT).count(),
        "review_count": review_count,
        "rating": float(shop.rating or 0),
        "views": views,
        "order_count": order_count,
        "revenue": int(revenue or 0),
        "stock_units": stock_units,
    }
