"""Заказы (§5.5 ТЗ): превью сумм, оформление, список/деталь, статус-машина."""

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cache_private
from apps.core.pagination import EnvelopePagination

from .models import Order
from .serializers import ShopOrderSerializer
from .services import advance_order, calc_totals, cancel_order, create_order


class OrdersView(APIView):
    """GET /orders/ — свои заказы; POST /orders/ — оформление; PUT — превью сумм (§5.5 ТЗ).

    PUT (превью) доступен без авторизации и без CSRF — exempt прописан
    в apps.core.middleware.ApiCsrfMiddleware. GET/POST — только владелец сессии.
    """

    serializer_class = serializers.Serializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["orders"], responses={200: None})
    def put(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        try:
            subtotal = int(data.get("subtotal") or 0)
        except (TypeError, ValueError):
            return Response(
                {"detail": "subtotal должен быть целым числом.", "fields": {"subtotal": "Целое число сумов."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subtotal < 0:
            return Response(
                {"detail": "subtotal не может быть отрицательным.", "fields": {"subtotal": "Неотрицательное целое."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delivery_method = (data.get("delivery_method") or "courier").strip()
        if delivery_method not in Order.DeliveryMethod.values:
            return Response(
                {
                    "detail": "Способ доставки: courier или pickup.",
                    "fields": {"delivery_method": "courier или pickup."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(calc_totals(subtotal, delivery_method, data.get("promo_code") or None))

    @extend_schema(tags=["orders"], operation_id="orders_list", responses={200: None, 401: None})
    def get(self, request):
        if not request.user.is_authenticated:
            raise NotAuthenticated()
        orders = (
            Order.objects.filter(user=request.user)
            .prefetch_related("items__seller", "events")
            .order_by("-created_at", "-id")
        )
        data = ShopOrderSerializer(orders, many=True, context={"request": request}).data
        return cache_private(Response(EnvelopePagination.whole_list(data)), request)

    @extend_schema(tags=["orders"], responses={201: None, 401: None})
    def post(self, request):
        if not request.user.is_authenticated:
            raise NotAuthenticated()
        data = request.data if isinstance(request.data, dict) else {}
        order = create_order(
            user=request.user,
            items=data.get("items") or [],
            delivery_method=(data.get("delivery_method") or "").strip(),
            payment_method=(data.get("payment_method") or "").strip(),
            address=data.get("address") or "",
            pickup_point=data.get("pickup_point") or "",
            comment=data.get("comment") or "",
            promo_code=data.get("promo_code") or None,
        )
        return Response({"id": order.pk, "detail": "Заказ оформлен"}, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """GET /orders/{id}/ — заказ доступен покупателю и продавцу позиции, иначе 404 (§5.5 ТЗ)."""

    serializer_class = serializers.Serializer

    @extend_schema(tags=["orders"], responses={200: None})
    def get(self, request, order_id: int):
        order = get_visible_order(request.user, order_id)
        data = ShopOrderSerializer(order, context={"request": request}).data
        return cache_private(Response(data), request)


class OrderStatusView(APIView):
    """POST /orders/{id}/status/ — advance (покупатель или продавец) / cancel (покупатель)."""

    serializer_class = serializers.Serializer

    @extend_schema(tags=["orders"], responses={200: None, 400: None, 403: None, 404: None})
    def post(self, request, order_id: int):
        order = get_visible_order(request.user, order_id)
        action = (request.data.get("action") or "").strip() if isinstance(request.data, dict) else ""
        if action == "advance":
            if not user_can_advance(request.user, order):
                return Response(
                    {"detail": "Менять статус заказа может только покупатель или продавец товара."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            order = advance_order(order)
        elif action == "cancel":
            if order.user_id != request.user.pk:
                return Response({"detail": "Отменить заказ может только покупатель."}, status=status.HTTP_403_FORBIDDEN)
            order = cancel_order(order)
        else:
            return Response(
                {"detail": "Неизвестное действие.", "fields": {"action": "advance или cancel."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": order.status, "detail": "Статус заказа обновлён"})


def is_order_seller(user, order) -> bool:
    if not user.is_authenticated:
        return False
    shop = getattr(user, "shop", None)
    return order.items.filter(seller_id=shop.pk).exists() if shop else False


def user_can_advance(user, order) -> bool:
    return order.user_id == user.pk or is_order_seller(user, order)


def get_visible_order(user, order_id: int) -> Order:
    """404 (а не 403) для чужих заказов — по ТЗ чужого заказа «не существует»."""
    from django.http import Http404

    try:
        order = Order.objects.prefetch_related("items__seller", "events").get(pk=order_id)
    except Order.DoesNotExist:
        raise Http404("Заказ не найден.") from None
    if order.user_id != user.pk and not is_order_seller(user, order):
        raise Http404("Заказ не найден.")
    return order
