import uuid

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([permissions.IsAuthenticated])
def upload_media(request):
    """
    Uploads a file straight to Supabase Storage and returns its public URL.
    The frontend can also upload directly with the Supabase JS client using a
    user-scoped signed policy -- this endpoint exists as a simple server-side
    fallback that keeps the SUPABASE_SERVICE_KEY off the client entirely.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"detail": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        return Response(
            {"detail": "Supabase is not configured on the backend (.env)."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    from supabase import create_client

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    folder = request.data.get("folder", "posts")
    ext = file_obj.name.split(".")[-1]
    path = f"{folder}/{request.user.id}/{uuid.uuid4()}.{ext}"

    supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).upload(
        path, file_obj.read(), {"content-type": file_obj.content_type}
    )
    public_url = supabase.storage.from_(settings.SUPABASE_MEDIA_BUCKET).get_public_url(path)
    return Response({"url": public_url, "path": path})
