"""
Removing a deleted account's uploaded files. Uploads live at
"<folder>/<user id>/<file>" (see views.upload_media), so only paths under the
user's own id are touched: shared files such as the demo videos in seed/
are never deleted.
"""
import logging
import re

from django.core.files.storage import default_storage

from . import storage
from .views import ALLOWED_FOLDERS

logger = logging.getLogger(__name__)


def uploaded_paths(user):
    """Storage paths of every file this user uploaded and still references. Call before deleting the user."""
    from accounts.models import Highlight
    from content.models import PostMedia, Reel, Story
    from social.models import Message

    urls = [user.avatar_url]
    urls += PostMedia.objects.filter(post__author=user).values_list("file_url", flat=True)
    urls += Story.objects.filter(author=user).values_list("file_url", flat=True)
    for reel in Reel.objects.filter(author=user).values("video_url", "thumbnail_url", "audio_url"):
        urls += reel.values()
    urls += Highlight.objects.filter(owner=user).values_list("cover_url", flat=True)
    urls += Message.objects.filter(sender=user).exclude(media_url="").values_list("media_url", flat=True)

    own = re.compile(rf"(?:{'|'.join(sorted(ALLOWED_FOLDERS))})/{re.escape(str(user.pk))}/[^/?#]+")
    return sorted({m.group(0) for url in urls if url for m in [own.search(url)] if m})


def delete_paths(paths):
    """Best effort: a storage hiccup must not undo or block an account deletion."""
    if not paths:
        return
    try:
        if storage.is_configured():
            storage.delete_many(paths)
        else:
            for path in paths:
                default_storage.delete(path)
    except Exception:  # noqa: BLE001 - logged for the team, never shown to the user
        logger.exception("Couldn't delete %d uploaded files of a deleted account", len(paths))
