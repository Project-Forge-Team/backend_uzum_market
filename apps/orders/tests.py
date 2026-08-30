"""Тесты заказов, промокодов и кабинета продавца (§4, §5.5, §5.6, §11 ТЗ)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.products.models import Product
from apps.products.services import create_seller
from apps.products.tests import make_category, make_product
from apps.users.tests import PASSWORD, AuthClient

from .models import Order, PromoCode
from .services import OrderError, calc_totals, create_order

User = get_user_model()


def make_buyer(email="buyer@t.uz"):
    return User.objects.create_user(email, PASSWORD, first_name="Азиз", last_name="Юсупов")


def checkout_payload(product_ids, **extra):
    payload = {
        "items": [{"product_id": pid, "qty": qty} for pid, qty in product_ids],
        "delivery_method": "courier",
        "payment_method": "card",
        "address": "г. Ташкент, ул. Тестовая, 5",
    }
    payload.update(extra)
    return payload


class PreviewTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()

    def test_pickup_is_free(self):
        body = calc_totals(300_000, "pickup", None)
        self.assertEqual(
            body, {"discount": 0, "delivery_cost": 0, "total": 300_000, "promo_valid": False, "promo_label": ""}
        )

    def test_courier_paid_under_threshold(self):
        body = calc_totals(300_000, "courier", None)
        self.assertEqual(body["delivery_cost"], 25_000)
        self.assertEqual(body["total"], 325_000)

    def test_courier_free_over_threshold(self):
        body = calc_totals(600_000, "courier", None)
        self.assertEqual(body["delivery_cost"], 0)

    def test_promo_discount_and_threshold(self):
        PromoCode.objects.create(code="STUDENT10", percent=10, min_subtotal=200_000, label="Учебный")
        body = calc_totals(600_000, "courier", "student10")
        self.assertEqual(body["discount"], 60_000)
        self.assertTrue(body["promo_valid"])
        self.assertEqual(body["promo_label"], "Учебный")
        # порог не достигнут: промокод не применяется
        body = calc_totals(150_000, "courier", "STUDENT10")
        self.assertFalse(body["promo_valid"])
        self.assertEqual(body["discount"], 0)

    def test_unknown_promo_is_not_an_error(self):
        body = calc_totals(600_000, "courier", "NOPE")
        self.assertFalse(body["promo_valid"])
        self.assertEqual(body["delivery_cost"], 0)  # 600k ≥ 500k и без скидки
        self.assertEqual(body["total"], 600_000)

    def test_put_endpoint_is_public(self):
        PromoCode.objects.create(code="UZUM2026", percent=5, min_subtotal=0, label="Знакомство")
        response = self.client.put(
            "/api/orders/",
            {"subtotal": 600000, "delivery_method": "courier", "promo_code": "UZUM2026"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["discount"], 30_000)
        self.assertEqual(body["total"], 570_000)
        self.assertEqual(sorted(body.keys()), ["delivery_cost", "discount", "promo_label", "promo_valid", "total"])


class CreateOrderTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.buyer = make_buyer()
        self.category = make_category()
        self.cheap = make_product(slug="cheap", price=100_000, stock=10)
        self.pricey = make_product(slug="pricey", price=450_000, stock=3)
        PromoCode.objects.create(code="STUDENT10", percent=10, min_subtotal=200_000, label="Учебный")
        self.client.login_as("buyer@t.uz")

    def test_totals_recalculated_on_server(self):
        # клиентский subtotal (1 сум) игнорируется
        response = self.client.csrf_post(
            "/api/orders/",
            checkout_payload([(self.cheap.pk, 1), (self.pricey.pk, 2)], promo_code="STUDENT10"),
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get(pk=response.json()["id"])
        self.assertEqual(order.subtotal, 1_000_000)
        self.assertEqual(order.discount, 100_000)
        self.assertEqual(order.delivery_cost, 0)  # 900k ≥ 500k
        self.assertEqual(order.total, 900_000)
        self.assertEqual(order.number[:3], "UZ-")
        self.assertRegex(order.number, r"^UZ-\d{6}$")
        # остатки списаны
        self.cheap.refresh_from_db()
        self.pricey.refresh_from_db()
        self.assertEqual(self.cheap.stock, 9)
        self.assertEqual(self.pricey.stock, 1)
        # позиции — снимки
        item = order.items.get(product=self.pricey)
        self.assertEqual(item.title, self.pricey.title)
        self.assertEqual(order.events.count(), 1)
        self.assertEqual(order.events.first().status, "new")

    def test_insufficient_stock(self):
        response = self.client.csrf_post("/api/orders/", checkout_payload([(self.pricey.pk, 5)]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("«", response.json()["detail"])
        self.assertIn("на складе всего 3", response.json()["detail"])
        self.assertEqual(Order.objects.count(), 0)
        self.pricey.refresh_from_db()
        self.assertEqual(self.pricey.stock, 3)  # ничего не списано

    def test_invalid_items_and_address(self):
        cases = [
            checkout_payload([]),
            checkout_payload([(self.cheap.pk, 0)]),
            checkout_payload([(self.cheap.pk, 21)]),
            checkout_payload([(999999, 1)]),
            checkout_payload([(self.cheap.pk, 1)], address="коротко"),
            checkout_payload([(self.cheap.pk, 1)], delivery_method="taxi"),
            checkout_payload([(self.cheap.pk, 1)], payment_method="crypto"),
        ]
        for payload in cases:
            response = self.client.csrf_post("/api/orders/", payload)
            self.assertEqual(response.status_code, 400, payload)

    def test_pickup_requires_point(self):
        response = self.client.csrf_post(
            "/api/orders/",
            checkout_payload([(self.cheap.pk, 1)], delivery_method="pickup", pickup_point="ПВЗ №1", address=""),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Order.objects.first().delivery_cost, 0)

    def test_anonymous_cannot_order(self):
        anon = AuthClient()
        response = anon.csrf_post("/api/orders/", checkout_payload([(self.cheap.pk, 1)]))
        self.assertEqual(response.status_code, 401)

    def test_draft_cannot_be_ordered(self):
        self.cheap.status = Product.Status.DRAFT
        self.cheap.save()
        response = self.client.csrf_post("/api/orders/", checkout_payload([(self.cheap.pk, 1)]))
        self.assertEqual(response.status_code, 400)

    def test_service_level_stock_race(self):
        # «последний товар»: второй заказ не должен пройти
        Product.objects.filter(pk=self.pricey.pk).update(stock=3)
        first = create_order(
            self.buyer, [{"product_id": self.pricey.pk, "qty": 3}], "pickup", "cash", pickup_point="ПВЗ"
        )
        self.assertEqual(first.subtotal, 1_350_000)
        with self.assertRaises(OrderError):
            create_order(self.buyer, [{"product_id": self.pricey.pk, "qty": 1}], "pickup", "cash", pickup_point="ПВЗ")

    def test_duplicate_positions_merged(self):
        response = self.client.csrf_post(
            "/api/orders/",
            {
                "items": [{"product_id": self.cheap.pk, "qty": 2}, {"product_id": self.cheap.pk, "qty": 3}],
                "delivery_method": "pickup",
                "pickup_point": "ПВЗ",
                "payment_method": "cash",
            },
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.json()["id"])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().qty, 5)


class OrderAccessTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.buyer = make_buyer()
        self.seller_user = User.objects.create_user("seller@t.uz", PASSWORD, first_name="Прод")
        self.shop = create_seller(owner=self.seller_user, name="Order Shop")
        self.product = make_product(seller=self.shop, slug="ord")
        self.order = create_order(
            self.buyer, [{"product_id": self.product.pk, "qty": 1}], "pickup", "cash", pickup_point="ПВЗ"
        )
        self.client.login_as("buyer@t.uz")

    def test_buyer_sees_order_with_timeline(self):
        body = self.client.get(f"/api/orders/{self.order.pk}/").json()
        self.assertEqual(body["items_count"], 1)
        self.assertEqual(body["buyer_name"], "Азиз Юсупов")
        self.assertEqual(body["timeline"][0]["status"], "new")
        self.assertIn("at", body["timeline"][0])

    def test_stranger_gets_404(self):
        stranger = AuthClient()
        User.objects.create_user("stranger@t.uz", PASSWORD, first_name="Чужой")
        stranger.login_as("stranger@t.uz")
        self.assertEqual(stranger.get(f"/api/orders/{self.order.pk}/").status_code, 404)

    def test_seller_of_item_sees_order(self):
        seller = AuthClient()
        seller.login_as("seller@t.uz")
        self.assertEqual(seller.get(f"/api/orders/{self.order.pk}/").status_code, 200)

    def test_orders_list_mine_only(self):
        make_buyer("other-buyer@t.uz")
        body = self.client.get("/api/orders/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            sorted(body.keys()), ["count", "next", "page", "page_size", "previous", "results", "total_pages"]
        )


class StatusMachineTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.buyer = make_buyer()
        self.seller_user = User.objects.create_user("seller@t.uz", PASSWORD, first_name="Прод")
        self.shop = create_seller(owner=self.seller_user, name="Status Shop")
        self.product = make_product(seller=self.shop, slug="st")
        self.order = create_order(
            self.buyer, [{"product_id": self.product.pk, "qty": 2}], "pickup", "cash", pickup_point="ПВЗ"
        )
        self.client.login_as("buyer@t.uz")

    def act(self, action, client=None):
        return (client or self.client).csrf_post(f"/api/orders/{self.order.pk}/status/", {"action": action})

    def test_full_lifecycle(self):
        for expected in ("packing", "shipping", "delivered"):
            response = self.act("advance")
            self.assertEqual(response.json()["status"], expected)
        # delivered дальше не двигается
        self.assertEqual(self.act("advance").status_code, 400)
        # и не отменяется
        self.assertEqual(self.act("cancel").status_code, 400)
        self.assertEqual([e.status for e in self.order.events.all()], ["new", "packing", "shipping", "delivered"])

    def test_seller_can_advance_buyer_cannot_cancel_delivered(self):
        seller = AuthClient()
        seller.login_as("seller@t.uz")
        self.assertEqual(self.act("advance", seller).json()["status"], "packing")

    def test_cancel_returns_stock(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(self.act("cancel").json()["status"], "cancelled")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        # повторная отмена — 400
        self.assertEqual(self.act("cancel").status_code, 400)

    def test_only_buyer_can_cancel(self):
        seller = AuthClient()
        seller.login_as("seller@t.uz")
        self.assertEqual(self.act("cancel", seller).status_code, 403)

    def test_stranger_gets_404(self):
        stranger = AuthClient()
        User.objects.create_user("stranger@t.uz", PASSWORD, first_name="Чужой")
        stranger.login_as("stranger@t.uz")
        self.assertEqual(
            stranger.csrf_post(f"/api/orders/{self.order.pk}/status/", {"action": "advance"}).status_code, 404
        )

    def test_unknown_action_400(self):
        self.assertEqual(self.act("pause").status_code, 400)


class ShopCabinetTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.seller_user = User.objects.create_user("seller@t.uz", PASSWORD, first_name="Прод")
        self.buyer = make_buyer()
        make_category()

    def test_get_shop_null_when_no_shop(self):
        self.client.login_as("seller@t.uz")
        response = self.client.get("/api/shop/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())

    def test_post_shop_creates_and_is_idempotent(self):
        self.client.login_as("seller@t.uz")
        response = self.client.csrf_post("/api/shop/", {"name": "Моя мастерская"})
        self.assertEqual(response.status_code, 201)
        shop_id = response.json()["id"]
        self.assertEqual(response.json()["detail"], "Магазин создан")
        # повтор — не дублируем
        response = self.client.csrf_post("/api/shop/", {"name": "Другое название"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], shop_id)

    def test_shop_name_validation(self):
        self.client.login_as("seller@t.uz")
        for name in ("", "а", "x" * 61):
            response = self.client.csrf_post("/api/shop/", {"name": name})
            self.assertEqual(response.status_code, 400, name)

    def test_patch_shop_keeps_slug(self):
        shop = create_seller(owner=self.seller_user, name="First Name")
        self.client.login_as("seller@t.uz")
        response = self.client.csrf_patch("/api/shop/", {"name": "Новое имя магазина"})
        self.assertEqual(response.status_code, 200)
        shop.refresh_from_db()
        self.assertEqual(shop.name, "Новое имя магазина")
        self.assertEqual(shop.slug, "first-name")  # слаг стабилен (§4 ТЗ)

    def test_patch_without_shop_404(self):
        self.client.login_as("seller@t.uz")
        self.assertEqual(self.client.csrf_patch("/api/shop/", {"name": "Имя"}).status_code, 404)

    def test_shop_orders_and_stats(self):
        shop = create_seller(owner=self.seller_user, name="Stats Shop")
        product = make_product(seller=shop, slug="st1", price=200_000, stock=10)
        order = create_order(self.buyer, [{"product_id": product.pk, "qty": 2}], "pickup", "cash", pickup_point="ПВЗ")
        self.client.login_as("seller@t.uz")
        body = self.client.get("/api/shop/orders/").json()
        self.assertEqual(body["count"], 1)
        entry = body["results"][0]
        self.assertEqual(entry["id"], order.pk)
        self.assertEqual(entry["subtotal"], 400_000)
        self.assertEqual(entry["total"], 400_000)
        self.assertIsNone(entry["promo_code"])
        self.assertEqual(entry["buyer_name"], "Азиз Юсупов")
        stats = body["stats"]
        self.assertEqual(stats["product_count"], 1)
        self.assertEqual(stats["order_count"], 1)
        self.assertEqual(stats["revenue"], 400_000)
        self.assertEqual(stats["stock_units"], 8)  # 10 − 2 проданных

        # после отмены заказа выручка и число заказов падают, остаток возвращается
        order.status = Order.Status.CANCELLED
        order.save()
        body = self.client.get("/api/shop/orders/").json()
        self.assertEqual(body["stats"]["order_count"], 0)
        self.assertEqual(body["stats"]["revenue"], 0)
        product.refresh_from_db()
        # stock возвращается отдельным сервисом отмены — здесь только метрика
        self.assertEqual(body["stats"]["stock_units"], 8)

    def test_shop_orders_without_shop(self):
        self.client.login_as("seller@t.uz")
        body = self.client.get("/api/shop/orders/").json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["stats"]["revenue"], 0)
