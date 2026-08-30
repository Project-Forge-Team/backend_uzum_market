"""Тесты каталога: товары, фильтры/фасеты, статусы, отзывы (§5.2–5.4, §11 ТЗ)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.orders.models import Order, OrderItem
from apps.users.tests import PASSWORD, AuthClient

from .models import Category, Product, Review, Seller
from .services import create_seller

User = get_user_model()

PRODUCT_FIELDS = {
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
}


def make_category(name="Электроника", slug="elektronika") -> Category:
    category, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name, "emoji": "📱", "color": "#EDE9FF"})
    return category


def make_product(**kwargs) -> Product:
    base_slug = kwargs.pop("slug", "testovyy-tovar-nomer-odin")
    slug, n = base_slug, 1
    while Product.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base_slug}-{n}"
    defaults = {
        "title": "Тестовый товар номер один",
        "slug": slug,
        "description": "Описание тестового товара длиной больше двадцати символов.",
        "price": 100_000,
        "stock": 10,
        "delivery_time": "Завтра",
        "brand": "TestBrand",
        "images": ["/products/gen/a-1.svg"],
        "characteristics": {"Вес": "1 кг"},
    }
    defaults.update(kwargs)
    seller = defaults.pop("seller", None) or make_seller()
    category = defaults.pop("category", None) or make_category()
    return Product.objects.create(seller=seller, category=category, **defaults)


def make_seller(name="Test Shop", owner=None) -> Seller:
    slug = name.lower().replace(" ", "-")
    seller, _ = Seller.objects.get_or_create(slug=slug, defaults={"name": name, "owner": owner})
    return seller


class CatalogContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = make_seller("Demo Shop")
        cls.category = make_category()
        cls.product = make_product(seller=cls.seller, category=cls.category, old_price=125_000)

    def test_categories_envelope_and_counts(self):
        make_category("Одежда", "odezhda")
        response = self.client.get("/api/categories/")
        body = response.json()
        self.assertEqual(
            sorted(body.keys()), ["count", "next", "page", "page_size", "previous", "results", "total_pages"]
        )
        self.assertTrue(all(isinstance(body[k], bool) for k in ("next", "previous")))
        by_slug = {c["slug"]: c for c in body["results"]}
        self.assertEqual(by_slug["elektronika"]["product_count"], 1)
        self.assertEqual(by_slug["odezhda"]["product_count"], 0)
        self.assertEqual(
            sorted(by_slug["elektronika"].keys()), ["color", "emoji", "id", "name", "product_count", "slug"]
        )

    def test_products_envelope_and_product_fields(self):
        response = self.client.get("/api/products/")
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertTrue(all(isinstance(body[k], bool) for k in ("next", "previous")))
        product = body["results"][0]
        self.assertEqual(set(product.keys()), PRODUCT_FIELDS)
        self.assertTrue(
            all(isinstance(product[k], int) for k in ("price", "old_price", "discount_percent", "stock", "views"))
        )
        self.assertEqual(product["discount_percent"], 20)  # (125k-100k)/125k
        self.assertEqual(product["monthly_payment"], {"months": 12, "per_month": 8400, "overpay": 0})
        self.assertEqual(product["image"], "/products/gen/a-1.svg")
        self.assertEqual(product["category"]["emoji"], "📱")
        self.assertIn("product_count", product["seller"])

    def test_dates_are_iso_utc_with_z(self):
        created = self.client.get("/api/products/").json()["results"][0]["created_at"]
        self.assertRegex(created, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    def test_old_price_ignored_when_not_a_discount(self):
        product = make_product(slug="b", old_price=90_000, title="Второй тестовый товар")
        body = self.client.get(f"/api/products/{product.pk}/").json()
        self.assertIsNone(body["old_price"])
        self.assertEqual(body["discount_percent"], 0)

    def test_page_size_clamped(self):
        # базовый товар из setUpTestData + 6 новых = 7
        for _ in range(6):
            make_product()
        self.assertEqual(len(self.client.get("/api/products/?page_size=2").json()["results"]), 4)
        self.assertEqual(len(self.client.get("/api/products/?page_size=500").json()["results"]), 7)
        self.assertEqual(len(self.client.get("/api/products/?page_size=junk").json()["results"]), 7)

    def test_q_search_by_title_and_brand(self):
        make_product(slug="b", title="Уникальный гитарный струнный набор", brand="CordX")
        self.assertEqual(self.client.get("/api/products/?q=гитарный").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?search=CordX").json()["count"], 1)

    def test_price_and_stock_filters(self):
        make_product(slug="cheap", price=10_000, stock=0, title="Дешёвый товар для фильтра")
        self.assertEqual(self.client.get("/api/products/?min_price=50000").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?max_price=50000").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?in_stock=1").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?discounted=1").json()["count"], 1)

    def test_facets_ignore_their_own_filter(self):
        other = make_category("Спорт", "sport")
        make_product(slug="cheap", price=10_000, stock=0, title="Дешёвый товар для фильтра")
        make_product(slug="c", category=other, price=777_000)
        body = self.client.get("/api/products/?min_price=500000").json()
        # ценовой фасет считается ДО фильтра по цене: ползунок не «уехал»
        self.assertEqual(body["count"], 1)  # остался только товар за 777 000
        self.assertEqual(body["facets"]["price"]["min"], 10_000)
        self.assertEqual(body["facets"]["price"]["max"], 777_000)
        # фасет категорий не учитывает фильтр по категории
        body = self.client.get("/api/products/?category=sport").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual({c["slug"] for c in body["facets"]["categories"]}, {"elektronika", "sport"})

    def test_ids_param_overrides_filters(self):
        first = self.client.get("/api/products/").json()["results"][0]["id"]
        body = self.client.get(f"/api/products/?ids={first}&min_price=99999999").json()
        self.assertEqual(body["count"], 1)

    def test_ordering_price(self):
        make_product(slug="z", price=10, title="Самый дешёвый товар из всех")
        prices = [p["price"] for p in self.client.get("/api/products/?ordering=price").json()["results"]]
        self.assertEqual(prices, sorted(prices))

    def test_sellers_list_sorted_by_rating(self):
        response = self.client.get("/api/sellers/")
        body = response.json()
        self.assertGreaterEqual(body["count"], 1)
        top = body["results"][0]
        self.assertIn("order_count", top)
        self.assertIn("created_at", top)

    def test_seller_detail_by_slug_with_products(self):
        body = self.client.get("/api/sellers/demo-shop/").json()
        self.assertEqual(body["slug"], "demo-shop")
        self.assertEqual(len(body["products"]), 1)
        self.assertEqual(self.client.get("/api/sellers/no-such-shop/").status_code, 404)

    def test_view_counter_increments_without_auth(self):
        before = self.client.get("/api/products/1/").json()["views"]
        response = self.client.post("/api/products/1/view/")
        self.assertEqual(response.json(), {"ok": True})
        after = self.client.get("/api/products/1/").json()["views"]
        self.assertEqual(after, before + 1)


class ProductVisibilityTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.owner = User.objects.create_user("owner@t.uz", PASSWORD, first_name="Влад")
        self.shop = create_seller(owner=self.owner, name="Owner Shop")
        self.active = make_product(seller=self.shop, slug="active")
        self.draft = make_product(seller=self.shop, slug="draft", status=Product.Status.DRAFT)
        User.objects.create_user("stranger@t.uz", PASSWORD, first_name="Чужой")

    def test_draft_hidden_from_strangers(self):
        response = self.client.get(f"/api/products/{self.draft.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/products/?status=draft").json()["count"], 0)
        self.client.login_as("stranger@t.uz")
        self.assertEqual(self.client.get("/api/products/?status=draft").json()["count"], 0)

    def test_draft_visible_to_owner_only(self):
        self.client.login_as("owner@t.uz")
        self.assertEqual(self.client.get(f"/api/products/{self.draft.pk}/").status_code, 200)
        body = self.client.get("/api/products/?status=draft").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["slug"], "draft")
        # и через ids владельцу
        self.assertEqual(self.client.get(f"/api/products/?ids={self.draft.pk}").json()["count"], 1)

    def test_mine_includes_all_statuses(self):
        self.client.login_as("owner@t.uz")
        body = self.client.get("/api/products/mine/").json()
        self.assertEqual({p["slug"] for p in body["results"]}, {"active", "draft"})

    def test_mine_without_shop(self):
        self.client.login_as("stranger@t.uz")
        response = self.client.get("/api/products/mine/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["results"], [])
        self.assertIn("магазина", body["detail"])

    def test_mine_requires_auth(self):
        self.assertEqual(self.client.get("/api/products/mine/").status_code, 401)


class ProductWriteTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.owner = User.objects.create_user("owner@t.uz", PASSWORD, first_name="Влад")
        self.shop = create_seller(owner=self.owner, name="Owner Shop")
        self.category = make_category()
        self.client.login_as("owner@t.uz")
        User.objects.create_user("stranger@t.uz", PASSWORD, first_name="Чужой")

    def payload(self, **extra):
        data = {
            "title": "Новый тестовый товар",
            "description": "Описание нового товара, более двадцати символов.",
            "price": 150_000,
            "stock": 5,
            "category_id": self.category.pk,
        }
        data.update(extra)
        return data

    def test_create_and_slug_translit(self):
        response = self.client.csrf_post("/api/products/", self.payload())
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["detail"], "Товар опубликован")
        product = Product.objects.get(pk=body["id"])
        self.assertEqual(product.slug, "novyy-testovyy-tovar")
        self.assertEqual(product.brand, "Без бренда")

    def test_create_without_shop_403(self):
        no_shop = AuthClient()
        User.objects.create_user("noshop@t.uz", PASSWORD, first_name="Без")
        no_shop.login_as("noshop@t.uz")
        self.assertEqual(no_shop.csrf_post("/api/products/", self.payload()).status_code, 403)

    def test_create_by_slug_category(self):
        payload = self.payload()
        payload.pop("category_id")
        payload["category"] = "elektronika"
        response = self.client.csrf_post("/api/products/", payload)
        self.assertEqual(response.status_code, 201, response.content)

    def test_validation_bounds(self):
        cases = [
            self.payload(title="Коротко"),
            self.payload(description="Слишком короткое"),
            self.payload(price=0),
            self.payload(stock=100_000),
            self.payload(images=[f"img{i}.svg" for i in range(9)]),
        ]
        for payload in cases:
            response = self.client.csrf_post("/api/products/", payload)
            self.assertEqual(response.status_code, 400, payload)
            body = response.json()
            self.assertIn("detail", body)
            self.assertTrue(all(isinstance(v, str) for v in body.get("fields", {}).values()))

    def test_patch_partial_merges_values(self):
        product = make_product(seller=self.shop, slug="x")
        # частичный PATCH: только stock; валидируются слитые значения
        self.assertEqual(self.client.csrf_patch(f"/api/products/{product.pk}/", {"stock": 3}).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock, 3)
        self.assertEqual(product.title, "Тестовый товар номер один")  # не пришло — не тронуто
        # слитая валидация: описание менять не просим, но title делаем коротким
        response = self.client.csrf_patch(f"/api/products/{product.pk}/", {"title": "коротко"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["fields"])

    def test_patch_by_stranger_403(self):
        product = make_product(seller=self.shop, slug="y")
        stranger = AuthClient()
        stranger.login_as("stranger@t.uz")
        self.assertEqual(stranger.csrf_patch(f"/api/products/{product.pk}/", {"stock": 1}).status_code, 403)

    def test_delete_cascades_reviews(self):
        product = make_product(seller=self.shop, slug="z")
        Review.objects.create(product=product, author="А", rating=5, text="Отличный товар, всем советую")
        response = self.client.csrf_delete(f"/api/products/{product.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Товар удалён")
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertFalse(Review.objects.exists())

    def test_status_endpoint_idempotent(self):
        product = make_product(seller=self.shop, slug="s1")
        response = self.client.csrf_post(f"/api/products/{product.pk}/status/", {"status": "draft"})
        self.assertEqual(response.json()["detail"], "Статус обновлён")
        product.refresh_from_db()
        self.assertEqual(product.status, "draft")
        # повтор с тем же статусом → 200 без изменений (§6.5 ТЗ)
        self.assertEqual(
            self.client.csrf_post(f"/api/products/{product.pk}/status/", {"status": "draft"}).status_code, 200
        )
        self.assertEqual(
            self.client.csrf_post(f"/api/products/{product.pk}/status/", {"status": "bogus"}).status_code, 400
        )


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.seller_user = User.objects.create_user("seller@t.uz", PASSWORD, first_name="Прод")
        self.shop = create_seller(owner=self.seller_user, name="Review Shop")
        self.buyer = User.objects.create_user("buyer@t.uz", PASSWORD, first_name="Азиз")
        self.other = User.objects.create_user("other@t.uz", PASSWORD, first_name="Федя")
        self.product = make_product(seller=self.shop)
        Review.objects.create(product=self.product, author="Прошлый", rating=3, text="Нормальный товар за свои деньги")

    def order_with(self, user, qty=1, status=Order.Status.SHIPPING):
        order = Order.objects.create(
            number="UZ-000001",
            user=user,
            subtotal=100,
            total=100,
            status=status,
            delivery_method=Order.DeliveryMethod.PICKUP,
            payment_method=Order.PaymentMethod.CASH,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            title=self.product.title,
            price=self.product.price,
            qty=qty,
            seller=self.shop,
        )
        return order

    def test_review_requires_purchase(self):
        self.client.login_as("other@t.uz")
        response = self.client.csrf_post(
            f"/api/products/{self.product.pk}/reviews/",
            {"rating": 5, "text": "Никогда не покупал, но хочется отзыв!"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("уже купили этот товар", response.json()["detail"])

    def test_review_full_flow(self):
        self.client.login_as("buyer@t.uz")
        # без покупки — нельзя
        self.assertEqual(
            self.client.csrf_post(
                f"/api/products/{self.product.pk}/reviews/", {"rating": 5, "text": "Хочу отзыв без покупки"}
            ).status_code,
            403,
        )
        body = self.client.get(f"/api/products/{self.product.pk}/reviews/").json()
        self.assertFalse(body["can_review"])
        self.assertEqual(body["purchases"], 0)

        # с покупкой — можно
        self.order_with(self.buyer, qty=2)
        body = self.client.get(f"/api/products/{self.product.pk}/reviews/").json()
        self.assertTrue(body["can_review"])
        self.assertEqual(body["purchases"], 2)

        response = self.client.csrf_post(
            f"/api/products/{self.product.pk}/reviews/",
            {"rating": 5, "text": "Купил и довольный, качество отличное!", "pros": "Качество"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["updated"])
        review_id = response.json()["id"]

        # второй POST = редактирование, строка одна
        response = self.client.csrf_post(
            f"/api/products/{self.product.pk}/reviews/", {"rating": 4, "text": "Чуть передумал, но всё равно хорошо"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["updated"])
        self.assertEqual(response.json()["id"], review_id)
        self.assertEqual(Review.objects.filter(user=self.buyer).count(), 1)

        # verified и own
        body = self.client.get(f"/api/products/{self.product.pk}/reviews/").json()
        mine = next(r for r in body["results"] if r["own"])
        self.assertTrue(mine["verified"])
        self.assertEqual(mine["initials"], "А")
        # summary согласован
        self.assertEqual(body["summary"]["count"], 2)

    def test_review_validation(self):
        self.order_with(self.buyer)
        self.client.login_as("buyer@t.uz")
        for payload in ({"rating": 9, "text": "Хороший товар, реально хороший"}, {"rating": 5, "text": "мало"}):
            response = self.client.csrf_post(f"/api/products/{self.product.pk}/reviews/", payload)
            self.assertEqual(response.status_code, 400)

    def test_verified_false_after_cancel(self):
        self.client.login_as("buyer@t.uz")
        order = self.order_with(self.buyer, status=Order.Status.NEW)
        self.client.csrf_post(
            f"/api/products/{self.product.pk}/reviews/", {"rating": 5, "text": "Успел написать отзыв!"}
        )
        order.status = Order.Status.CANCELLED
        order.save()
        body = self.client.get(f"/api/products/{self.product.pk}/reviews/").json()
        mine = next(r for r in body["results"] if r["own"])
        self.assertFalse(mine["verified"])  # verified считается по живым заказам

    def test_reply_and_delete_permissions(self):
        self.order_with(self.buyer)
        self.client.login_as("buyer@t.uz")
        review_id = self.client.csrf_post(
            f"/api/products/{self.product.pk}/reviews/", {"rating": 5, "text": "Товар пришёл быстро и целый"}
        ).json()["id"]

        # ответить может только владелец магазина
        self.assertEqual(
            self.client.csrf_post(f"/api/reviews/{review_id}/reply/", {"reply": "Спасибо за отзыв!"}).status_code, 403
        )
        seller_client = AuthClient()
        seller_client.login_as("seller@t.uz")
        self.assertEqual(
            seller_client.csrf_post(f"/api/reviews/{review_id}/reply/", {"reply": "Спасибо, приходите ещё!"}).json()[
                "detail"
            ],
            "Ответ опубликован",
        )
        self.assertEqual(seller_client.csrf_post(f"/api/reviews/{review_id}/reply/", {"reply": "ок"}).status_code, 400)

        # удалить может продавец (а автор — свой)
        self.assertEqual(seller_client.csrf_delete(f"/api/reviews/{review_id}/").status_code, 200)
        other = AuthClient()
        other.login_as("other@t.uz")
        self.assertEqual(other.csrf_delete(f"/api/reviews/{review_id}/").status_code, 404)

    def test_review_updates_product_aggregates(self):
        self.order_with(self.buyer)
        self.client.login_as("buyer@t.uz")
        self.client.csrf_post(f"/api/products/{self.product.pk}/reviews/", {"rating": 5, "text": "Великолепный товар!"})
        self.product.refresh_from_db()
        self.assertEqual(self.product.reviews_count, 2)
        self.assertEqual(float(self.product.rating), 4.0)  # (3+5)/2
        breakdown = {row["stars"]: row["count"] for row in self.product.rating_breakdown}
        self.assertEqual(breakdown[5], 1)
        self.assertEqual(breakdown[3], 1)

    def test_draft_product_review_404(self):
        draft = make_product(seller=self.shop, slug="d", status=Product.Status.DRAFT)
        self.client.login_as("buyer@t.uz")
        self.assertEqual(self.client.get(f"/api/products/{draft.pk}/reviews/").status_code, 404)
