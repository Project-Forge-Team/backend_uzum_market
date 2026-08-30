"""Тесты авторизации (§3, §5.1 ТЗ)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = "Password123"


def csrf_of(client: APIClient) -> str:
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200, response.content
    return response.json()["csrf"]


class AuthClient(APIClient):
    """Клиент с автоматическим X-CSRFToken из куки (как фронт)."""

    def csrf_post(self, path, data=None, format="json", **extra):
        extra.setdefault(
            "HTTP_X_CSRFTOKEN",
            self.cookies.get(settings.CSRF_COOKIE_NAME).value
            if settings.CSRF_COOKIE_NAME in self.cookies
            else csrf_of(self),
        )
        return self.post(path, data, format=format, **extra)

    def csrf_patch(self, path, data=None, **extra):
        extra.setdefault(
            "HTTP_X_CSRFTOKEN",
            self.cookies.get(settings.CSRF_COOKIE_NAME).value
            if settings.CSRF_COOKIE_NAME in self.cookies
            else csrf_of(self),
        )
        return self.patch(path, data, format="json", **extra)

    def csrf_put(self, path, data=None, **extra):
        extra.setdefault(
            "HTTP_X_CSRFTOKEN",
            self.cookies.get(settings.CSRF_COOKIE_NAME).value
            if settings.CSRF_COOKIE_NAME in self.cookies
            else csrf_of(self),
        )
        return self.put(path, data, format="json", **extra)

    def csrf_delete(self, path, **extra):
        extra.setdefault(
            "HTTP_X_CSRFTOKEN",
            self.cookies.get(settings.CSRF_COOKIE_NAME).value
            if settings.CSRF_COOKIE_NAME in self.cookies
            else csrf_of(self),
        )
        return self.delete(path, **extra)

    def login_as(self, email: str, password: str = PASSWORD):
        csrf = csrf_of(self)
        response = self.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200, response.content
        return response


def make_user(email="user@example.com", password=PASSWORD, **kwargs):
    kwargs.setdefault("first_name", "Тест")
    return User.objects.create_user(email=email, password=password, **kwargs)


class CsrfFlowTests(TestCase):
    def setUp(self):
        self.client = AuthClient()

    def test_csrf_issues_cookie_and_token(self):
        response = self.client.get("/api/auth/csrf/")
        body = response.json()
        self.assertEqual(body["detail"], "CSRF cookie issued")
        cookie = response.cookies[settings.CSRF_COOKIE_NAME]
        self.assertEqual(cookie.value, body["csrf"])
        self.assertNotIn("HttpOnly", cookie.output())  # фронт читает куку из JS
        self.assertIn("Lax", cookie.output())

    def test_unsafe_request_without_csrf_is_403(self):
        response = self.client.post("/api/auth/login/", {"email": "a@b.uz", "password": "x"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CSRF-токен не совпал. Обновите страницу.")

    def test_csrf_header_must_match_cookie(self):
        token = csrf_of(self.client)
        response = self.client.post(
            "/api/auth/login/", {"email": "a@b.uz", "password": "x"}, format="json", HTTP_X_CSRFTOKEN="wrong"
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/api/auth/login/", {"email": "a@b.uz", "password": "x"}, format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 401)


class LoginTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        self.user = make_user("buyer@test.uz")

    def test_login_sets_both_cookies_and_returns_profile(self):
        response = self.client.login_as("buyer@test.uz")
        body = response.json()
        self.assertEqual(
            sorted(body.keys()),
            ["date_joined", "email", "first_name", "id", "is_seller", "last_name", "phone", "seller_id"],
        )
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME].value)
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME].value)

    def test_login_wrong_password_is_401_with_detail(self):
        csrf = csrf_of(self.client)
        response = self.client.post(
            "/api/auth/login/",
            {"email": "buyer@test.uz", "password": "nope-nope"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("Неверный email или пароль", response.json()["detail"])

    def test_login_is_case_insensitive(self):
        self.client.login_as("BUYER@test.uz")

    def test_me_requires_session(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Вы не авторизованы")

    def test_me_returns_profile_with_session(self):
        self.client.login_as("buyer@test.uz")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "buyer@test.uz")

    def test_logout_clears_session(self):
        self.client.login_as("buyer@test.uz")
        response = self.client.csrf_post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Вы вышли из аккаунта")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)


class RegisterTests(TestCase):
    def setUp(self):
        self.client = AuthClient()

    def register(self, payload):
        return self.client.csrf_post("/api/auth/register/", payload)

    def test_register_creates_user_and_shop(self):
        response = self.register(
            {
                "email": "New@User.UZ",
                "password": PASSWORD,
                "password2": PASSWORD,
                "first_name": "Сардор",
                "last_name": "Каримов",
                "phone": "+998901112233",
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["email"], "new@user.uz")
        self.assertTrue(body["is_seller"])
        self.assertIsNotNone(body["seller_id"])
        # магазин «1 к 1», имя по умолчанию «<имя> — магазин»
        from apps.products.models import Seller

        seller = Seller.objects.get(pk=body["seller_id"])
        self.assertEqual(seller.name, "Сардор — магазин")
        self.assertEqual(seller.city, "Ташкент")
        # куки стоят сразу
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_register_with_shop_name(self):
        response = self.register(
            {
                "email": "a@b.uz",
                "password": PASSWORD,
                "password2": PASSWORD,
                "first_name": "Имя",
                "shop_name": "Моя мастерская",
            }
        )
        from apps.products.models import Seller

        seller = Seller.objects.get(pk=response.json()["seller_id"])
        self.assertEqual(seller.name, "Моя мастерская")
        self.assertNotIn(" ", seller.slug)

    def test_register_validation_fields(self):
        response = self.register(
            {
                "email": "not-an-email",
                "password": "short",
                "password2": "other",
                "first_name": "И",
            }
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("detail", body)
        fields = body.get("fields", {})
        for key in ("email", "password", "password2", "first_name"):
            self.assertIn(key, fields)
            self.assertIsInstance(fields[key], str)

    def test_register_duplicate_email(self):
        make_user("dup@test.uz")
        response = self.register(
            {"email": "DUP@test.uz", "password": PASSWORD, "password2": PASSWORD, "first_name": "Имя"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["fields"])


class MePatchTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        make_user("me@test.uz", first_name="Старое")
        self.client.login_as("me@test.uz")

    def test_patch_updates_fields(self):
        response = self.client.csrf_patch("/api/auth/me/", {"first_name": "Новое", "phone": "+998901234567"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["first_name"], "Новое")
        self.assertEqual(body["phone"], "+998901234567")

    def test_patch_email_conflict(self):
        make_user("other@test.uz")
        response = self.client.csrf_patch("/api/auth/me/", {"email": "other@test.uz"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["fields"])


class PasswordTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        make_user("pwd@test.uz")
        self.client.login_as("pwd@test.uz")

    def test_password_change_and_other_sessions_invalidated(self):
        # вторая сессия того же пользователя
        other = AuthClient()
        other.login_as("pwd@test.uz")
        self.assertEqual(other.get("/api/auth/me/").status_code, 200)

        response = self.client.csrf_post("/api/auth/password/", {"current": PASSWORD, "next": "NewPassword456"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Пароль обновлён")

        # текущая сессия жива, вторая — мертва
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(other.get("/api/auth/me/").status_code, 401)
        # новый пароль работает
        fresh = AuthClient()
        fresh.login_as("pwd@test.uz", "NewPassword456")

    def test_password_wrong_current(self):
        response = self.client.csrf_post("/api/auth/password/", {"current": "wrong-pass", "next": "NewPassword456"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("current", response.json()["fields"])

    def test_password_too_short(self):
        response = self.client.csrf_post("/api/auth/password/", {"current": PASSWORD, "next": "short"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("next", response.json()["fields"])


class ThrottleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # locmem общий на процесс: история троттлинга не должна течь между тестами

    def test_login_throttled_by_ip(self):
        from django.test import override_settings

        client = AuthClient()
        csrf = csrf_of(client)
        with override_settings(
            REST_FRAMEWORK={
                **settings.REST_FRAMEWORK,
                "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "3/min"},
            }
        ):
            codes = [
                client.post(
                    "/api/auth/login/",
                    {"email": "x@y.uz", "password": "bad-pass-1"},
                    format="json",
                    HTTP_X_CSRFTOKEN=csrf,
                ).status_code
                for _ in range(5)
            ]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3], 429)


class SessionHousekeepingTests(TestCase):
    def test_sessions_live_in_db_and_expire(self):
        self.assertEqual(Session.objects.count(), 0)
        client = AuthClient()
        make_user("s@test.uz")
        client.login_as("s@test.uz")
        self.assertEqual(Session.objects.count(), 1)
        session = Session.objects.first()
        decoded = session.get_decoded()
        self.assertEqual(decoded["_auth_user_id"], str(User.objects.get(email="s@test.uz").pk))
