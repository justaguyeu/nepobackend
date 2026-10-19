import io
import uuid

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from uploads import storage


class Command(BaseCommand):
    help = "Uploads a tiny test image to Supabase Storage, checks its public URL loads, then deletes it."

    def handle(self, *args, **options):
        if not storage.is_configured():
            raise CommandError("SUPABASE_URL / SUPABASE_SERVICE_KEY aren't set, so uploads go to local media instead.")
        if not storage.has_server_key():
            raise CommandError(storage.KEY_HELP)

        buf = io.BytesIO()
        Image.new("RGB", (1, 1), "white").save(buf, "PNG")
        path = f"checks/{uuid.uuid4()}.png"
        try:
            url = storage.upload(path, buf.getvalue(), "image/png")
        except storage.StorageError as exc:
            raise CommandError(f"Upload failed: {exc}")

        try:
            status = httpx.get(url, timeout=storage.TIMEOUT).status_code
        finally:
            storage.delete(path)
        if status != 200:
            raise CommandError(
                f"Uploaded, but its public URL returned HTTP {status}. "
                f"Make the '{settings.SUPABASE_MEDIA_BUCKET}' bucket public in Supabase Storage."
            )
        self.stdout.write(self.style.SUCCESS(
            f"Supabase Storage works: uploads to '{settings.SUPABASE_MEDIA_BUCKET}' succeed and are publicly readable."
        ))
