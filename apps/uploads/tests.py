"""Тесты загрузки файлов (§7 ТЗ)."""

import struct
import zlib

from django.test import TestCase

from apps.users.tests import PASSWORD, AuthClient

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n"
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(
        b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    )
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(
        b"IDAT", zlib.compress(b"\x00\xff\x00\x00")
    )
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(b"IEND", b"")
)


class UploadFlowTests(TestCase):
    def setUp(self):
        self.client = AuthClient()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user("u@t.uz", PASSWORD, first_name="Тест")
        self.client.login_as("u@t.uz")

    def upload(self, filename="shot.png", content_type="image/png", content=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        file = SimpleUploadedFile(filename, content if content is not None else PNG_1x1, content_type=content_type)
        return self.client.csrf_post("/api/uploads/", {"file": file}, format="multipart")

    def test_upload_and_serve(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["name"], "shot.png")
        self.assertTrue(body["url"].startswith("/api/uploads/"))
        key = body["url"].rsplit("/", 1)[1]
        self.assertRegex(key, r"^[0-9a-z]+-[0-9a-f]{8}\.(png|jpg|webp|gif)$")  # <base36>-<hex8><ext>

        served = self.client.get(body["url"])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "image/png")
        self.assertIn("immutable", served["Cache-Control"])
        self.assertEqual(b"".join(served.streaming_content), PNG_1x1)

    def test_wrong_content_type_rejected(self):
        self.assertEqual(self.upload(content_type="text/plain", content=b"hello").status_code, 400)

    def test_too_large_rejected(self):
        big = b"\x89" + b"0" * (2 * 1024 * 1024 + 1)
        self.assertEqual(self.upload(content=big).status_code, 400)

    def test_requires_auth_and_csrf(self):
        anon = AuthClient()
        from django.core.files.uploadedfile import SimpleUploadedFile

        file = SimpleUploadedFile("shot.png", PNG_1x1, content_type="image/png")
        self.assertEqual(anon.csrf_post("/api/uploads/", {"file": file}, format="multipart").status_code, 401)
        # без CSRF-заголовка — 403
        self.client.handler  # noqa: B018
        file2 = SimpleUploadedFile("shot.png", PNG_1x1, content_type="image/png")
        self.assertEqual(self.client.post("/api/uploads/", {"file": file2}).status_code, 403)

    def test_unknown_key_404(self):
        self.assertEqual(self.client.get("/api/uploads/does-not-exist.png").status_code, 404)
        self.assertEqual(self.client.get("/api/uploads/../etc/passwd").status_code, 404)
