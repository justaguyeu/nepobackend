import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, UnidentifiedImageError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

# The folder becomes part of the storage path, so only accept known values.
ALLOWED_FOLDERS = {"posts", "reels", "stories", "avatars", "messages", "highlights"}

# Extension -> content type we store/serve it with. Never trust the client's
# content type: an "image" uploaded as text/html or image/svg+xml could run
# script when opened from our storage domain.
IMAGE_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp",
}
VIDEO_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm", "m4v": "video/x-m4v"}
IMAGE_ONLY_FOLDERS = {"avatars", "highlights"}


class UploadThrottle(UserRateThrottle):
    """Per-user upload limit (rate in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["uploads"])."""
    scope = "uploads"


def _reject(message):
    return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([UploadThrottle])
def upload_media(request: Request):
    """
    Uploads a file to Supabase Storage (when configured) or falls back to
    local Django media storage so the app works in dev without Supabase.
    Returns {"url": "<public URL>", "path": "<storage path>"}.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return _reject("No file provided")

    folder = request.data.get("folder", "posts")
    if folder not in ALLOWED_FOLDERS:
        return _reject(f"folder must be one of {sorted(ALLOWED_FOLDERS)}")

    ext = file_obj.name.rsplit(".", 1)[-1].lower() if "." in file_obj.name else ""
    if ext in IMAGE_TYPES:
        content_type, limit = IMAGE_TYPES[ext], settings.MAX_IMAGE_UPLOAD_BYTES
    elif ext in VIDEO_TYPES and folder not in IMAGE_ONLY_FOLDERS:
        content_type, limit = VIDEO_TYPES[ext], settings.MAX_VIDEO_UPLOAD_BYTES
    else:
        allowed = IMAGE_TYPES if folder in IMAGE_ONLY_FOLDERS else {**IMAGE_TYPES, **VIDEO_TYPES}
        return _reject(f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")

    if file_obj.size > limit:
        return _reject(f"File is too large (max {limit // (1024 * 1024)} MB).")

    data = file_obj.read()
    if content_type.startswith("image/"):
        # Make sure it really is an image of the claimed kind, not a renamed script/HTML file.
        try:
            with Image.open(ContentFile(data)) as img:
                img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            return _reject("That file isn't a valid image.")

    storage_path = f"{folder}/{request.user.id}/{uuid.uuid4()}.{ext}"

    # ── Supabase path ────────────────────────────────────────────────────────
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        try:
            from supabase import create_client
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
            supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).upload(
                storage_path, data, {"content-type": content_type}
            )
            public_url = supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).get_public_url(storage_path)
            return Response({"url": public_url, "path": storage_path})
        except Exception:
            # Don't echo storage internals (bucket names, keys in URLs) back to the client.
            return Response({"detail": "Upload to storage failed. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)

    # ── Local fallback (dev) ─────────────────────────────────────────────────
    saved_path = default_storage.save(storage_path, ContentFile(data))
    # Build an absolute URL the frontend can use
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    media_url = settings.MEDIA_URL.rstrip("/")
    public_url = f"{scheme}://{host}{media_url}/{saved_path}"
    return Response({"url": public_url, "path": saved_path})
