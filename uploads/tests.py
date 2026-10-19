import base64
import io
import json
import shutil
import tempfile
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework.test import APITestCase

from . import storage

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(buf, "PNG")
    return buf.getvalue()


@override_settings(MEDIA_ROOT=MEDIA, SUPABASE_URL="", SUPABASE_SERVICE_KEY="")
class UploadTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_authenticate(User.objects.create_user(username="alice", password="pw123456"))

    def upload(self, name, content, folder="posts"):
        return self.client.post("/api/uploads/", {"file": SimpleUploadedFile(name, content), "folder": folder}, format="multipart")

    def test_valid_image(self):
        res = self.upload("photo.png", png_bytes())
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["url"].endswith(".png"))

    def test_rejects_disallowed_types(self):
        self.assertEqual(self.upload("evil.svg", b"<svg onload=alert(1)>").status_code, 400)
        self.assertEqual(self.upload("page.html", b"<script>alert(1)</script>").status_code, 400)

    def test_rejects_fake_image(self):
        self.assertEqual(self.upload("fake.png", b"<script>alert(1)</script>").status_code, 400)

    def test_rejects_video_avatar_and_bad_folder(self):
        self.assertEqual(self.upload("clip.mp4", b"\x00" * 10, folder="avatars").status_code, 400)
        self.assertEqual(self.upload("photo.png", png_bytes(), folder="../etc").status_code, 400)

    @override_settings(MAX_IMAGE_UPLOAD_BYTES=10)
    def test_rejects_oversized(self):
        self.assertEqual(self.upload("photo.png", png_bytes()).status_code, 400)


def jwt_key(role):
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"


SUPABASE = {"SUPABASE_URL": "https://proj.supabase.co", "SUPABASE_MEDIA_BUCKET": "nepo-media"}


class KeyRoleTests(SimpleTestCase):
    def test_key_role(self):
        self.assertEqual(storage.key_role(jwt_key("service_role")), "service_role")
        self.assertEqual(storage.key_role(jwt_key("anon")), "anon")
        self.assertEqual(storage.key_role("sb_secret_abc123"), "secret")
        self.assertEqual(storage.key_role("sb_publishable_abc123"), "publishable")
        self.assertIsNone(storage.key_role("not-a-key"))

    @override_settings(**SUPABASE, SUPABASE_SERVICE_KEY=jwt_key("anon"))
    def test_system_check_flags_public_key(self):
        self.assertEqual([w.id for w in storage.check_key(None)], ["uploads.W001"])


@override_settings(**SUPABASE)
class SupabaseUploadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="pw123456")
        self.client.force_authenticate(self.user)

    def upload(self, folder="posts"):
        return self.client.post(
            "/api/uploads/", {"file": SimpleUploadedFile("photo.png", png_bytes()), "folder": folder}, format="multipart"
        )

    @patch("uploads.storage.httpx.request")
    def test_uploads_with_service_role_key(self, request):
        key = jwt_key("service_role")
        request.return_value = httpx.Response(200, json={"Key": "nepo-media/x"})
        with override_settings(SUPABASE_SERVICE_KEY=key):
            res = self.upload(folder="avatars")
        self.assertEqual(res.status_code, 200, res.data)
        method, url = request.call_args.args
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"https://proj.supabase.co/storage/v1/object/nepo-media/{res.data['path']}")
        self.assertTrue(res.data["path"].startswith(f"avatars/{self.user.id}/"))
        self.assertEqual(res.data["url"], f"https://proj.supabase.co/storage/v1/object/public/nepo-media/{res.data['path']}")
        self.assertEqual(headers["Authorization"], f"Bearer {key}")
        self.assertEqual(headers["Content-Type"], "image/png")

    @patch("uploads.storage.httpx.request")
    def test_secret_key_is_sent_only_as_apikey(self, request):
        request.return_value = httpx.Response(200, json={})
        with override_settings(SUPABASE_SERVICE_KEY="sb_secret_abc123"):
            self.assertEqual(self.upload().status_code, 200)
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(headers["apikey"], "sb_secret_abc123")
        self.assertNotIn("Authorization", headers)

    @patch("uploads.storage.httpx.request")
    def test_public_key_is_refused_without_calling_supabase(self, request):
        with override_settings(SUPABASE_SERVICE_KEY=jwt_key("anon")), self.assertLogs("uploads.views", "ERROR"):
            res = self.upload()
        self.assertEqual(res.status_code, 503)
        request.assert_not_called()

    @patch("uploads.storage.httpx.request")
    def test_supabase_error_is_logged_not_echoed(self, request):
        request.return_value = httpx.Response(403, json={"message": "new row violates row-level security policy"})
        with override_settings(SUPABASE_SERVICE_KEY=jwt_key("service_role")), self.assertLogs("uploads.views", "ERROR") as logs:
            res = self.upload()
        self.assertEqual(res.status_code, 502)
        self.assertNotIn("security policy", str(res.data))
        self.assertIn("row-level security", "\n".join(logs.output))
