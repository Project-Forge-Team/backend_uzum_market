"""Тесты авторизации.

Каждый тест закрывает конкретный баг из AUDIT.md — так расхождение «docs vs код»
больше не вернётся незаметно.
"""

import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

User = get_user_model()

PASSWORD = "Str0ng-Pass-99"


def register(client, email="user@example.com", **extra):
    payload = {"email": email, "password": PASSWORD, "password2": PASSWORD}
    payload.update(extra)
    return client.post("/api/auth/register/", payload, format="json")


class RegisterTests(APITestCase):
    def test_sets_cookies_and_no_tokens_in_body(self):
        """AUDIT B-2: токены не уезжают в теле, но cookie ставятся — клиент залогинен сразу."""
        response = register(self.client, first_name="Ivan", phone="+998901234567")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertNotIn("access", body)
        self.assertNotIn("refresh", body)
        self.assertEqual(body["email"], "user@example.com")
        self.assertEqual(body["first_name"], "Ivan")
        cookies = {c.key: c for c in self.client.cookies.values()}
        self.assertIn("uzum_access_token", cookies)
        self.assertIn("uzum_refresh_token", cookies)
        self.assertTrue(cookies["uzum_access_token"]["httponly"])

    def test_email_normalized_and_me_works(self):
        response = register(self.client, email="  PrObe@Example.COM  ")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get().email, "probe@example.com")
        self.assertEqual(self.client.get("/api/auth/me/").json()["email"], "probe@example.com")

    def test_duplicate_email_different_case_is_400_not_500(self):
        register(self.client, email="user@example.com")
        response = register(self.client, email="USER@example.com")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_password_mismatch(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "a@b.co", "password": PASSWORD, "password2": "another-one"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password2", response.json())

    def test_weak_password_rejected(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "a@b.co", "password": "12345678", "password2": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_phone_validation(self):
        response = register(self.client, phone="не-телефон")
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="user@example.com", password=PASSWORD)

    def test_login_case_insensitive(self):
        """AUDIT B-5: регистрация lower()-ит email, поэтому вход обязан быть регистронезависимым."""
        response = self.client.post(
            "/api/auth/login/", {"email": "UsEr@Example.COM", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.id)

    def test_wrong_password(self):
        response = self.client.post(
            "/api/auth/login/", {"email": "user@example.com", "password": "nope-nope-nope"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cookie_flags_follow_settings(self):
        self.client.post("/api/auth/login/", {"email": "user@example.com", "password": PASSWORD}, format="json")
        cookie = self.client.cookies["uzum_access_token"]
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(int(cookie["max-age"]), int(timedelta(seconds=2).total_seconds()))
        # refresh не светится на весь домен
        self.assertEqual(self.client.cookies["uzum_refresh_token"]["path"], "/api/auth/")

    @override_settings(
        JWT_COOKIE={
            "ACCESS": "uzum_access_token",
            "REFRESH": "uzum_refresh_token",
            "CSRF_NAME": "csrftoken",
            "SECURE": True,
            "SAMESITE": "None",
            "HTTP_ONLY": True,
            "ACCESS_PATH": "/",
            "REFRESH_PATH": "/api/auth/",
            "DOMAIN": None,
        }
    )
    def test_cross_site_mode_requires_csrf_header(self):
        """AUDIT A-1: при SameSite=None cookie шлются на любой сайт → без CSRF-токена отказ."""
        denied = self.client.post(
            "/api/auth/login/", {"email": "user@example.com", "password": PASSWORD}, format="json"
        )
        self.assertEqual(denied.status_code, 403)

        from django.conf import settings as st

        csrf = self.client.get("/api/auth/csrf/")
        self.assertEqual(csrf.status_code, 200)
        token = self.client.cookies[st.JWT_COOKIE["CSRF_NAME"]].value
        allowed = self.client.post(
            "/api/auth/login/",
            {"email": "user@example.com", "password": PASSWORD},
            format="json",
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_login_is_throttled(self):
        """AUDIT C-3: перебор паролей должен упираться в лимит, а не в бесконечность."""
        from django.conf import settings

        limited = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"login": "3/min", "register": "3/min", "refresh": "3/min"},
        }
        with override_settings(REST_FRAMEWORK=limited):
            codes = [
                self.client.post(
                    "/api/auth/login/", {"email": "user@example.com", "password": "bad-password-1"}, format="json"
                ).status_code
                for _ in range(6)
            ]
        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codes)


class TokenLifecycleTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="user@example.com", password=PASSWORD)
        login = self.client.post("/api/auth/login/", {"email": "user@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_refresh_accepts_form_encoded_body(self):
        """AUDIT A-3: 500 AttributeError на неизменяемом QueryDict."""
        response = self.client.post(
            "/api/auth/refresh/",
            data="",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 204)

    def test_refresh_accepts_no_body_and_updates_access_cookie(self):
        before = self.client.cookies["uzum_access_token"].value
        response = self.client.post("/api/auth/refresh/")
        self.assertEqual(response.status_code, 204)
        self.assertNotEqual(self.client.cookies["uzum_access_token"].value, before)

    def test_refresh_body_token_takes_precedence_over_cookie(self):
        """Явный refresh в теле важнее cookie: битый токен не должен «проходить» за счёт cookie."""
        register(self.client, email="body@example.com")
        cookie_value = self.client.cookies["uzum_refresh_token"].value
        self.client.cookies["uzum_refresh_token"] = "garbage"
        # 1) валидный токен в теле + битая cookie -> успех (приоритет у тела)
        ok = self.client.post("/api/auth/refresh/", data={"refresh": cookie_value}, format="json")
        self.assertEqual(ok.status_code, 204)
        # 2) тело без refresh -> читаем cookie (в jar после шага 1 лежит ротированный refresh)
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 204)
        # 3) битый токен в теле + валидная cookie -> 401, а не тихий 204; cookies сбрасываются
        bad = self.client.post("/api/auth/refresh/", data={"refresh": "garbage"}, format="json")
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.client.cookies["uzum_refresh_token"].value, "")

    def test_refresh_without_cookie_clears_cookies(self):
        self.client.cookies.clear()
        response = self.client.post("/api/auth/refresh/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Refresh token not found in cookies.")

    def test_logout_blacklists_refresh_token(self):
        """AUDIT A-5: logout обязан отозвать refresh, а не только стереть cookies."""
        self.assertEqual(BlacklistedToken.objects.count(), 0)
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        # и после этого refresh больше не работает
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 401)

    def test_logout_allowed_without_valid_access_token(self):
        """Logout не должен требовать живой access, иначе cookie не очистить."""
        self.client.cookies["uzum_access_token"] = "garbage"
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)

    def test_rotation_invalidates_old_refresh_cookie(self):
        """ROTATE_REFRESH_TOKENS=True: старый refresh после ротации не работает."""
        old_refresh = self.client.cookies["uzum_refresh_token"].value
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 204)
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import RefreshToken

        with self.assertRaises(TokenError):
            RefreshToken(old_refresh)  # должен быть в блэклисте

    def test_expired_access_token_yields_401_on_protected_only(self):
        """AUDIT A-4: истёкший/битый токен = 401 на /me/, но 200 на публичном каталоге."""
        self.client.cookies["uzum_access_token"] = "not-a-jwt"
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/products/").status_code, 200)
        self.assertEqual(self.client.get("/api/categories/").status_code, 200)


class MeViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="user@example.com", password=PASSWORD)

    def test_anonymous_401(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_bearer_token_supported(self):
        """AUDIT B-2: заголовочный флоу должен работать (мобильные клиенты)."""
        from rest_framework_simplejwt.tokens import RefreshToken

        access = str(RefreshToken.for_user(self.user).access_token)
        response = self.client.get("/api/auth/me/", headers={"authorization": f"Bearer {access}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "user@example.com")

    def test_inactive_user_rejected(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        access = str(RefreshToken.for_user(self.user).access_token)
        self.assertEqual(
            self.client.get("/api/auth/me/", headers={"authorization": f"Bearer {access}"}).status_code, 401
        )

    def test_deleted_user_does_not_crash(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        access = str(RefreshToken.for_user(self.user).access_token)
        self.user.delete()
        self.assertEqual(
            self.client.get("/api/auth/me/", headers={"authorization": f"Bearer {access}"}).status_code, 401
        )


class EnsureSuperuserTests(TestCase):
    """Идемпотентное создание/повышение суперюзера (build.sh, шаг «Суперюзер»).

    Закрывает падение деплоя `CommandError: That Email is already taken.`:
    раньше build.sh парсил stdout `manage.py shell -c` (где баннер засорял вывод),
    поэтому guard никогда не срабатывал и деплой уходил в `createsuperuser --noinput`,
    который бросал CommandError на уже существующем email.
    """

    def _call(self, **opts):
        out = io.StringIO()
        call_command("ensure_superuser", stdout=out, **opts)
        return out.getvalue()

    def setUp(self):
        User.objects.all().delete()

    def test_creates_superuser_when_absent(self):
        self._call(email="boss@example.com", password=PASSWORD, first_name="Bob")
        user = User.objects.get(email="boss@example.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.first_name, "Bob")

    def test_repeated_run_is_noop_and_keeps_password(self):
        self._call(email="boss@example.com", password=PASSWORD)
        user = User.objects.get(email="boss@example.com")
        before = user.password
        out = self._call(email="boss@example.com", password="another-new-password-123")
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.password, before)  # пароль без --update-password не трогаем
        self.assertIn("уже в порядке", out)

    def test_legacy_mixed_case_email_is_promoted_and_normalized(self):
        # «Наследный» профиль с email в смешанном регистре (записан до нормализации).
        user = User.objects.create_user(email="admin@example.com", password=PASSWORD)
        User.objects.filter(pk=user.pk).update(email="Admin@Example.com")
        count_before = User.objects.count()

        out = self._call(email="Admin@Example.com", password=PASSWORD)
        User.objects.get(email="admin@example.com")  # нормализован, не дубль
        self.assertEqual(User.objects.count(), count_before)
        refreshed = User.objects.get(pk=user.pk)
        self.assertTrue(refreshed.is_staff)
        self.assertTrue(refreshed.is_superuser)
        self.assertEqual(refreshed.email, "admin@example.com")
        self.assertTrue(refreshed.check_password(PASSWORD))  # хэш не сброшен
        self.assertIn("обновлён", out)

    def test_update_password_changes_existing_password(self):
        self._call(email="boss@example.com", password=PASSWORD)
        user = User.objects.get(email="boss@example.com")
        self._call(email="boss@example.com", password="brand-new-Pass-42", update_password=True)
        user.refresh_from_db()
        self.assertTrue(user.check_password("brand-new-Pass-42"))
        self.assertFalse(user.check_password(PASSWORD))

    def test_empty_email_is_skipped(self):
        from unittest.mock import patch

        # build.sh полагается на env-путь: DJANGO_SUPERUSER_EMAIL пуст → пропуск, rc 0.
        with patch.dict("os.environ", {"DJANGO_SUPERUSER_EMAIL": ""}, clear=False):
            out = self._call()
        self.assertEqual(User.objects.count(), 0)
        self.assertIn("не задан", out)

    def test_create_without_password_raises_command_error(self):
        with self.assertRaises(CommandError):
            self._call(email="boss@example.com", password="")
