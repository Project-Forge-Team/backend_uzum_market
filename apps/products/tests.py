"""Тесты каталога: форма ответа, фильтры, пагинация, кэш, количество запросов.

Покрывают пункты AUDIT.md B-1/B-4/D-2/D-4/D-6.
"""

from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, Product, Seller


class CatalogTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.electronics = Category.objects.create(name="Электроника", slug="electronics")
        cls.beauty = Category.objects.create(name="Красота", slug="beauty")
        cls.tech = Seller.objects.create(name="TechStore", rating=Decimal("4.50"), reviews_count=340)
        cls.beauty_seller = Seller.objects.create(name="Glam", rating=Decimal("4.90"), reviews_count=10)

        cls.cheap = Product.objects.create(
            title="Наушники AirPods Pro 2",
            description="Активное шумоподавление",
            price=Decimal("1000.00"),
            old_price=Decimal("2000.00"),
            rating=Decimal("4.95"),
            reviews_count=450,
            monthly_payment=Decimal("83.00"),
            delivery_time="1 день",
            image="https://cdn.example.com/a.jpg",
            images=["https://cdn.example.com/a1.jpg", "https://cdn.example.com/a2.jpg"],
            characteristics={"Вес": "5 г"},
            is_ad=True,
            category=cls.electronics,
            seller=cls.tech,
        )
        cls.expensive = Product.objects.create(
            title="Фен Dyson Supersonic",
            description="Цифровой мотор V9",
            price=Decimal("9000.00"),
            old_price=None,
            rating=Decimal("4.10"),
            reviews_count=7,
            delivery_time="2 дня",
            image="products/dyson.jpg",
            category=cls.beauty,
            seller=cls.beauty_seller,
        )


class ProductListContractTests(CatalogTestCase):
    def test_list_shape_and_external_image_not_mangled(self):
        """AUDIT B-1: внешний URL картинки не должен превращаться в /media/https%3A/…"""
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("count", "page_size", "total_pages", "next", "previous", "results"):
            self.assertIn(key, payload)

        first = payload["results"][0]
        self.assertNotIn("%3A", first["image"])
        self.assertEqual(
            sorted(first.keys()),
            sorted(
                [
                    "id",
                    "title",
                    "price",
                    "old_price",
                    "discount_percent",
                    "rating",
                    "reviews_count",
                    "monthly_payment",
                    "delivery_time",
                    "image",
                    "is_ad",
                    "category",
                    "created_at",
                ]
            ),
        )

    def test_local_media_path_becomes_absolute(self):
        row = self.client.get(f"/api/products/{self.expensive.id}/").json()
        self.assertEqual(row["image"], "http://testserver/media/products/dyson.jpg")

    def test_detail_payload_has_heavy_fields(self):
        row = self.client.get(f"/api/products/{self.expensive.id}/").json()
        self.assertIn("description", row)
        self.assertIn("characteristics", row)
        self.assertIn("seller", row)
        self.assertIn("updated_at", row)

    def test_discount_percent_computed_on_backend(self):
        cheap = self.client.get(f"/api/products/{self.cheap.id}/").json()
        self.assertEqual(cheap["discount_percent"], 50)
        full = self.client.get(f"/api/products/{self.expensive.id}/").json()
        self.assertEqual(full["discount_percent"], 0)

    def test_rating_and_price_are_strings_of_exact_decimal(self):
        """float давал 4.9499999… в JSON."""
        row = self.client.get(f"/api/products/{self.cheap.id}/").json()
        self.assertEqual(row["rating"], "4.95")
        self.assertEqual(row["price"], "1000.00")

    def test_list_defers_description(self):
        """D-4: в списке нет description/characteristics — экономия трафика."""
        row = self.client.get("/api/products/").json()["results"][0]
        self.assertNotIn("description", row)
        self.assertNotIn("characteristics", row)


class PaginationAndFilterTests(CatalogTestCase):
    def test_page_size_param_works(self):
        """AUDIT B-4: параметр был в API.md, но игнорировался."""
        self.assertEqual(len(self.client.get("/api/products/?page_size=1").json()["results"]), 1)
        self.assertEqual(self.client.get("/api/products/?page_size=1").json()["page_size"], 1)

    def test_page_size_is_clamped(self):
        response = self.client.get("/api/products/?page_size=100000")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.json()["page_size"], 50)

    def test_price_range_filters(self):
        self.assertEqual(self.client.get("/api/products/?min_price=5000").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?max_price=5000").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?min_price=1&max_price=99999").json()["count"], 2)

    def test_category_seller_is_ad_filters(self):
        self.assertEqual(self.client.get(f"/api/products/?category={self.electronics.id}").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?category_slug=beauty").json()["count"], 1)
        self.assertEqual(self.client.get(f"/api/products/?seller={self.tech.id}").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?is_ad=true").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?discounted=true").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?min_rating=4.5").json()["count"], 1)

    def test_search(self):
        self.assertEqual(self.client.get("/api/products/?search=Dyson").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?search=шумоподавление").json()["count"], 1)

    def test_ordering_by_reviews_count(self):
        """AUDIT B-4: поле не было в allowlist → сортировка молча не применялась."""
        ids = [row["id"] for row in self.client.get("/api/products/?ordering=reviews_count").json()["results"]]
        self.assertEqual(ids, [self.expensive.id, self.cheap.id])

    def test_ordering_by_price_desc(self):
        titles = [row["title"] for row in self.client.get("/api/products/?ordering=-price").json()["results"]]
        self.assertEqual(titles[0], "Фен Dyson Supersonic")

    def test_unknown_query_param_is_400(self):
        """Лучше явная 400, чем 200 с проигнорированным фильтром."""
        response = self.client.get("/api/products/?category=1&min_price=abc")
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/products/?pages=2")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pages", response.json()["query"][0])

    def test_bad_page_number_is_404(self):
        self.assertEqual(self.client.get("/api/products/?page=999").status_code, 404)


class QueryCountTests(CatalogTestCase):
    def test_list_uses_select_related(self):
        """D-2/N+1: список = 1 запрос на страницу + 1 на count."""
        with self.assertNumQueries(2):
            response = self.client.get("/api/products/?page_size=100")
        self.assertEqual(response.status_code, 200)

    def test_detail_single_query(self):
        with self.assertNumQueries(1):
            self.client.get(f"/api/products/{self.cheap.id}/")


class CacheTests(CatalogTestCase):
    def test_list_is_cached_and_invalidated_on_save(self):
        """D-6: списки кэшируются, но любое изменение каталога сбрасывает версию ключа."""
        first = self.client.get("/api/products/").json()["count"]
        self.assertEqual(self.client.get("/api/products/").json()["count"], first)

        Product.objects.create(
            title="Новый товар",
            price=Decimal("10.00"),
            delivery_time="1 день",
            category=self.electronics,
        )
        self.assertEqual(self.client.get("/api/products/").json()["count"], first + 1)

    def test_cache_disabled_setting(self):
        with override_settings(CATALOG_CACHE_SECONDS=0):
            self.client.get("/api/categories/")
            self.client.get("/api/categories/")

    def test_categories_and_sellers_ok(self):
        self.assertEqual(self.client.get("/api/categories/").json()["count"], 2)
        self.assertEqual(self.client.get("/api/sellers/").json()["count"], 2)
        self.assertEqual(self.client.get(f"/api/categories/{self.electronics.id}/").json()["slug"], "electronics")


class RouterTests(CatalogTestCase):
    def test_api_root_lists_endpoints(self):
        payload = self.client.get("/api/").json()
        self.assertIn("products", payload)
        self.assertIn("categories", payload)
        self.assertIn("sellers", payload)

    def test_swagger_and_schema_available(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/schema/swagger-ui/").status_code, 200)
        self.assertEqual(self.client.get("/api/schema/redoc/").status_code, 200)

    def test_404_is_json_not_html(self):
        response = self.client.get("/api/products/0/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())


class CompressionTests(CatalogTestCase):
    def test_json_is_gzipped(self):
        response = self.client.get("/api/products/", headers={"accept_encoding": "gzip"})
        self.assertEqual(response.get("Content-Encoding"), "gzip")
