"""Тесты служебных эндпоинтов (health, demo/reset) и формата ошибок."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.products.models import Category, Product, Review, Seller
from apps.users.tests import PASSWORD, AuthClient

User = get_user_model()


class HealthTests(TestCase):
    def test_health_shape(self):
        Product.objects.create(
            title="Тестовый товар аж два",
            slug="t1",
            description="Описание товара больше двадцати символов",
            price=1,
            stock=0,
            category=Category.objects.create(name="К", slug="k"),
            seller=Seller.objects.create(name="S", slug="s"),
        )
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "uzum-market-clone")
        self.assertIn("backend", body)
        self.assertEqual(body["products"], 1)
        self.assertRegex(body["time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class SeedTests(TestCase):
    def test_seed_dataset_matches_spec(self):
        call_command("seed", "--reset", stdout=None)
        self.assertEqual(Category.objects.count(), 10)
        self.assertEqual(Seller.objects.count(), 10)
        self.assertEqual(Product.objects.count(), 52)  # 51 активных + 1 черновик
        self.assertEqual(Product.objects.filter(status=Product.Status.DRAFT).count(), 1)
        self.assertEqual(Review.objects.count(), 102)
        self.assertEqual(User.objects.filter(email="buyer@uzum.uz").exists(), True)
        buyer = User.objects.get(email="buyer@uzum.uz")
        self.assertGreaterEqual(buyer.orders.count(), 2)
        # seed идемпотентен: повтор без --reset ничего не ломает и не дублирует
        call_command("seed", stdout=None)
        self.assertEqual(Product.objects.count(), 52)
        self.assertEqual(Review.objects.count(), 102)

    def test_svg_media_written_and_served(self):
        from apps.products.gen_media import write_svg

        write_svg("test-product-1.svg", "📱", "Brand", 0)
        response = self.client.get("/products/gen/test-product-1.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")


class DemoResetTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        call_command("seed", "--reset", stdout=None)

    def test_anonymous_reset_401(self):
        self.assertEqual(self.client.csrf_post("/api/demo/reset/").status_code, 401)

    def test_reset_restores_state_and_logs_out(self):
        self.client.login_as("buyer@uzum.uz")
        # нагадим
        Product.objects.all().delete()
        response = self.client.csrf_post("/api/demo/reset/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 52)
        self.assertEqual(Review.objects.count(), 102)
        # сессия сброшена
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_locked_demo_403(self):
        from django.test import override_settings

        self.client.login_as("buyer@uzum.uz")
        with override_settings(LOCK_DEMO=True):
            response = self.client.csrf_post("/api/demo/reset/")
        self.assertEqual(response.status_code, 403)


class ErrorShapeTests(TestCase):
    def test_404_is_json_with_detail(self):
        response = self.client.get("/api/products/999999/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

    def test_validation_error_shape(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "bad", "password": "1", "password2": "2", "first_name": "И"},
            format="json",
            HTTP_X_CSRFTOKEN="whatever",
        )
        # CSRF не прошёл бы без куки: сначала получим токен
        client = AuthClient()
        response = client.csrf_post(
            "/api/auth/register/",
            {"email": "bad", "password": "1", "password2": "2", "first_name": "И"},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIsInstance(body["detail"], str)
        for value in body["fields"].values():
            self.assertIsInstance(value, str)


class CachePolicyTests(TestCase):
    def test_public_catalog_cached_public(self):
        response = self.client.get("/api/products/")
        self.assertIn("max-age=15", response.get("Cache-Control", ""))

    def test_private_endpoints_no_store(self):
        client = AuthClient()
        User.objects.create_user("p@t.uz", PASSWORD, first_name="Тест")
        client.login_as("p@t.uz")
        for path in ("/api/auth/me/", "/api/orders/", "/api/products/mine/", "/api/shop/", "/api/shop/orders/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("no-store", response.get("Cache-Control", ""), path)
