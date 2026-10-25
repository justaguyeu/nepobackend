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

`python manage.py seed_data` **deletes every non-superuser account** (and
everything they posted), then fills the database with a Tanzanian demo
community: 100 accounts (74 businesses across the real business categories,
26 customers) with African profile photos, business profiles with
hours/contact info, photo and video posts, reels, stories with polls,
highlights, comments with replies, likes, saves, follows and follow
requests, notifications, and chats. A brand new person who registers
immediately has businesses to follow and content to see.

Every seeded account's password is **`password123`** (e.g. username
`mama_doreen_kitchen` or `furahamushi`). Run the command again any time to
reset to a clean demo state.

Media: photos are hotlinked from Unsplash (free Unsplash License); the short
videos ship in `accounts/seed/clips/` (from Pexels, free license) and are
uploaded once to the Supabase bucket's `seed/` folder. Without Supabase
settings, they go to local media storage (DEBUG only).

To seed the production database from your own machine, with the Supabase
values in `backend/.env` (PowerShell):

```powershell
$env:DATABASE_URL="<Render database -> External Database URL>"
python manage.py seed_data
Remove-Item Env:DATABASE_URL
```

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
- Run `seed_data` against production only if you want demo accounts there:
  it deletes every non-superuser account first.

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
