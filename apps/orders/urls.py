"""Маршруты заказов и кабинета продавца (§5.5–5.6 ТЗ)."""

from django.urls import path

from .order_views import OrderDetailView, OrderStatusView, OrdersView
from .shop_views import ShopOrdersView, ShopView

urlpatterns = [
    path("orders/", OrdersView.as_view(), name="orders"),
    path("orders/<int:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:order_id>/status/", OrderStatusView.as_view(), name="order-status"),
    path("shop/", ShopView.as_view(), name="shop"),
    path("shop/orders/", ShopOrdersView.as_view(), name="shop-orders"),
]
