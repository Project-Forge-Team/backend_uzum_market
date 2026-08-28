"""Тесты настроек (то, что нельзя проверить через HTTP).

`config.settings` импортируется в рантайме теста, поэтому проверяем только те функции,
которые можно вызвать повторно; сами значения настроек сверяются через `JWT_COOKIE`.
"""

import os
from unittest import mock

from django.test import SimpleTestCase

from config.settings import _url_prefix


class UrlPrefixTests(SimpleTestCase):
    """`_url_prefix` — страховка от «тихих» 404 на `/media/` и `/static/` (см. AUDIT B-7)."""

    def _check(self, value, expected):
        with mock.patch.dict(os.environ, {"MEDIA_URL": value}):
            self.assertEqual(_url_prefix("MEDIA_URL", "/media/"), expected)

    def test_relative_value_gets_leading_and_trailing_slash(self):
        for raw in ("media", "/media", "media/", "//media//"):
            with self.subTest(raw=raw):
                self._check(raw, "/media/")

    def test_empty_or_garbage_value_falls_back_to_default(self):
        for raw in ("", "   ", "/", "//"):
            with self.subTest(raw=raw):
                self._check(raw, "/media/")

    def test_absolute_url_is_kept_with_trailing_slash(self):
        self._check("https://cdn.example.com/media", "https://cdn.example.com/media/")
        self._check("http://localhost:9000/bucket/media/", "http://localhost:9000/bucket/media/")


class JwtCookieSettingsTests(SimpleTestCase):
    """Пути cookie должны соответствовать префиксу API, иначе refresh не найдёт токен."""

    def test_cookie_paths(self):
        from django.conf import settings

        self.assertEqual(settings.JWT_COOKIE["ACCESS_PATH"], "/")
        self.assertEqual(settings.JWT_COOKIE["REFRESH_PATH"], "/api/auth/")
        self.assertTrue(settings.JWT_COOKIE["HTTP_ONLY"])

    def test_refresh_cookie_path_covers_refresh_endpoint(self):
        """Path cookie обязан покрывать URL эндпоинта, иначе браузер не отдаст refresh."""
        from django.conf import settings
        from django.urls import reverse

        endpoint = reverse("refresh")
        cookie_path = settings.JWT_COOKIE["REFRESH_PATH"]
        self.assertTrue(
            endpoint.startswith(cookie_path),
            f"{endpoint} вне cookie path {cookie_path!r} — refresh не получит токен",
        )

    def test_csrf_cookie_name_is_not_django_default(self):
        """Имя `csrftoken` занято CsrfViewMiddleware: double-submit на нём рассинхронизируется
        (Middleware перезаписывает cookie на csrf_exempt-вьюхах) и даёт плавающие 403."""
        from django.conf import settings

        self.assertNotEqual(settings.JWT_COOKIE["CSRF_NAME"], "csrftoken")
