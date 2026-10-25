"""
Supabase Storage over its REST API. Calling the API directly (rather than
through the supabase SDK) works with both the legacy service_role JWT and the
newer sb_secret_ keys, which the SDK version we used rejected outright, and
gives large video uploads more than the SDK's 20-second timeout.
"""
import base64
import json
from urllib.parse import quote

import httpx
from django.conf import settings
from django.core import checks

# Videos can be up to MAX_VIDEO_UPLOAD_BYTES; give them time to reach Supabase.
TIMEOUT = httpx.Timeout(120, connect=10)

# Only these keys may write to storage on the server's behalf. anon and
# publishable keys are public: Storage policies block them from uploading.
SERVER_KEY_ROLES = {"service_role", "secret"}

KEY_HELP = (
    "SUPABASE_SERVICE_KEY is a public (anon/publishable) key, so Supabase Storage refuses "
    "every upload. Set it to the project's service_role key (or an sb_secret_ key) from "
    "Supabase dashboard -> Project Settings -> API Keys, then restart the server."
)


class StorageError(Exception):
    """Supabase refused or failed a request. The message is for server logs only."""


def key_role(key):
    """
    The role a Supabase API key acts as: "service_role"/"anon" for legacy JWT
    keys, "secret"/"publishable" for sb_ keys, None if it isn't a Supabase key.
    """
    if key.startswith("sb_"):
        return key.split("_")[1]
    try:
        payload = key.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("role")
    except (IndexError, ValueError, AttributeError):
        return None


def is_configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def has_server_key():
    return key_role(settings.SUPABASE_SERVICE_KEY) in SERVER_KEY_ROLES


def check_key(app_configs, **kwargs):
    """System check: flags a public key at startup instead of on the first failed upload."""
    if is_configured() and not has_server_key():
        return [checks.Warning(KEY_HELP, id="uploads.W001")]
    return []


def _headers():
    key = settings.SUPABASE_SERVICE_KEY
    headers = {"apikey": key}
    if not key.startswith("sb_"):
        # Legacy JWT keys also authorize the request; sb_ keys are only valid as apikey.
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _object_url(path, public=False):
    base = settings.SUPABASE_URL.rstrip("/")
    kind = "object/public" if public else "object"
    return f"{base}/storage/v1/{kind}/{settings.SUPABASE_MEDIA_BUCKET}/{quote(path)}"


def _request(method, path, **kwargs):
    try:
        res = httpx.request(method, _object_url(path), timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise StorageError(f"Couldn't reach Supabase Storage: {exc!r}") from exc
    if res.status_code >= 300:
        raise StorageError(f"Supabase Storage returned {res.status_code}: {res.text[:500]}")
    return res


def public_url(path):
    return _object_url(path, public=True)


def exists(path):
    """True if path is already in the (public) media bucket."""
    try:
        return httpx.head(public_url(path), timeout=TIMEOUT).status_code == 200
    except httpx.HTTPError:
        return False


def upload(path, data, content_type):
    """Stores data at path in the media bucket and returns its public URL."""
    _request(
        "POST", path, content=data,
        headers={**_headers(), "Content-Type": content_type, "Cache-Control": "max-age=3600", "x-upsert": "false"},
    )
    return public_url(path)


def delete(path):
    _request("DELETE", path, headers=_headers())
