# Nepo — backend

Django REST API for Nepo, a business-first social platform for Tanzanian
entrepreneurs and creators (feed, stories, reels, DMs, business profiles).

## Stack

- Django 5 + Django REST Framework
- SimpleJWT auth (7-day access tokens, 30-day refresh)
- SQLite locally, swappable to Supabase/managed Postgres for production
- Media (avatars, post/reel/story files) stored in Supabase Storage, not
  Django's local storage — see `uploads/views.py`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then fill in real values
python manage.py migrate
python manage.py seed_data       # optional but recommended — see below
python manage.py createsuperuser # optional, for /admin/
python manage.py runserver
```

The API is now at `http://localhost:8000/api/`, and the admin site at
`http://localhost:8000/admin/`.

## Demo data

`python manage.py seed_data` populates the database with a realistic demo
network: ~35 users (mix of personal and business accounts), business
profiles with categories/hours/contact info, posts with images and videos,
hashtags, comments, likes, stories, reels, saved posts, notifications, and
DM conversations. This means a brand new person who registers on the
frontend immediately has people to follow and content to see, instead of
landing in an empty app.

Every seeded account's password is **`password123`** (e.g. username
`amanimrema`). Run the command again any time to reset back to a clean
demo state — it flushes non-superuser data by default. Use
`python manage.py seed_data --no-flush` to add to the existing data instead
of wiping it first.

## Deploying (Render)

- **Build command:** `./build.sh` (installs requirements *and* runs
  `python manage.py migrate`; without the migrate step new columns/tables
  won't exist and requests will fail).
- **Start command:** `gunicorn nepo.wsgi`
- **Environment variables** (Render dashboard, not a committed `.env`):
  `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `CSRF_TRUSTED_ORIGINS`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
  `SUPABASE_MEDIA_BUCKET`. Leave `DJANGO_DEBUG` unset in production.
  The app refuses to start without `DJANGO_SECRET_KEY` when DEBUG is off.

## Security notes

- Login tokens: 30-minute access tokens, 30-day refresh tokens that rotate on
  every use and are revoked on logout (`POST /api/auth/logout/`). Changing the
  password revokes every existing token.
- Rate limits: login/register/password change 10/min per client, uploads
  60/min per user (see `REST_FRAMEWORK` in `nepo/settings.py`).
- Passwords go through Django's validators (length, common-password,
  similarity, numeric-only).
- Registration requires accepting the Terms & Conditions; the time and terms
  version are stored on the user (`terms_accepted_at`, `terms_version`).
  Bump `TERMS_VERSION` here and in `frontend/src/lib/terms.ts` together.
- Private accounts: posts, reels, stories, comments and follower lists are
  only visible to the owner and accepted followers.
- Uploads: images (jpg/png/gif/webp, 10 MB, verified with Pillow) and videos
  (mp4/mov/webm/m4v, 100 MB); the stored content type is chosen by the server.

## Environment variables

See `.env.example` for the full list. At minimum for local development you
need `DJANGO_SECRET_KEY` set to *something*; Supabase variables can stay
blank locally (media uploads just won't work until they're set).

**Before deploying to production:**
- Set a real, secret `DJANGO_SECRET_KEY` (never reuse the dev one).
- Set `DJANGO_DEBUG=False`.
- Set `DJANGO_ALLOWED_HOSTS` to your real domain(s).
- Set `CORS_ALLOWED_ORIGINS` to your real frontend origin(s).
- Point `DATABASES` at Postgres (Supabase or otherwise) instead of SQLite —
  see the commented-out block in `nepo/settings.py`.
- Fill in the real `SUPABASE_*` values so uploads work.
- Re-run `seed_data` only if you actually want demo accounts in production;
  otherwise skip it and let real users register.

## Apps

| App        | Responsibility                                           |
|------------|------------------------------------------------------------|
| `accounts` | Custom user model, registration/login, highlights          |
| `content`  | Posts, media, comments, likes, stories, reels, hashtags     |
| `social`   | Follows, notifications, conversations, messages             |
| `business` | Business categories and business profiles                   |
| `uploads`  | Proxies file uploads to Supabase Storage                     |

## Tests

```bash
python manage.py test
```
