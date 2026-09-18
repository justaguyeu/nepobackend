import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([permissions.IsAuthenticated])
def upload_media(request: Request):
    """
    Uploads a file to Supabase Storage (when configured) or falls back to
    local Django media storage so the app works in dev without Supabase.
    Returns {"url": "<public URL>", "path": "<storage path>"}.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"detail": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

    folder = request.data.get("folder", "posts")
    ext = file_obj.name.rsplit(".", 1)[-1].lower() if "." in file_obj.name else "jpg"
    unique_name = f"{uuid.uuid4()}.{ext}"
    storage_path = f"{folder}/{request.user.id}/{unique_name}"

    # ── Supabase path ────────────────────────────────────────────────────────
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        try:
            from supabase import create_client
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
            supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).upload(
                storage_path, file_obj.read(), {"content-type": file_obj.content_type}
            )
            public_url = supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).get_public_url(storage_path)
            return Response({"url": public_url, "path": storage_path})
        except Exception as exc:
            return Response(
                {"detail": f"Supabase upload failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # ── Local fallback (dev) ─────────────────────────────────────────────────
    saved_path = default_storage.save(storage_path, ContentFile(file_obj.read()))
    # Build an absolute URL the frontend can use
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    media_url = settings.MEDIA_URL.rstrip("/")
    public_url = f"{scheme}://{host}{media_url}/{saved_path}"
    return Response({"url": public_url, "path": saved_path})
