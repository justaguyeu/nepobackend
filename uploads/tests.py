import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

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
