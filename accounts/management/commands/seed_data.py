"""
Replaces every non-superuser account with a lively demo community: 100
Tanzanian business owners and customers (74 businesses across the real
business categories, 26 people), with posts, video posts, reels, stories,
highlights, comments and replies, likes, saves, follows, follow requests,
notifications and chats.

All photos are African, most of them from Tanzania (see accounts/seed/media.py).
The short videos ship with the code in accounts/seed/clips/ and are uploaded
once to Supabase Storage (seed/ folder) when it is configured, otherwise to
local media storage.

Run with:  python manage.py seed_data
Against production from your own machine (PowerShell):
    $env:DATABASE_URL="<Render External Database URL>"; python manage.py seed_data

Superusers are kept, everyone else is deleted first. Every seeded account's
password is "password123".
"""
import random
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import cycle

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Highlight
from accounts.seed import content as text
from accounts.seed.media import CLIP_DIR, CLIPS, MEN, PHOTOS, WOMEN, avatar, photo, post_image, story_image
from business.models import BusinessCategory, BusinessProfile
from content.models import (
    Comment, Hashtag, Like, Post, PostMedia, Reel, ReelComment, SavedPost, Story, StorySticker, StoryView,
)
from social.models import Conversation, Follow, Message, Notification
from uploads import storage

User = get_user_model()
PASSWORD = "password123"
BATCH = 500


@dataclass
class Member:
    """A seeded account plus what the seed needs to know to post as it."""
    user: object
    pools: list
    place: tuple
    business: bool
    popularity: float
    own_photos: list = field(default_factory=list)
    posts: list = field(default_factory=list)


@contextmanager
def manual_timestamps():
    """
    Lets the seed set created_at (and viewed_at) itself, so the feed spans
    weeks instead of every row being stamped with the same second.
    """
    fields = [
        f for label in ("accounts", "content", "social", "business")
        for model in apps.get_app_config(label).get_models()
        for f in model._meta.concrete_fields if getattr(f, "auto_now_add", False)
    ]
    for f in fields:
        f.auto_now_add = False
    try:
        yield
    finally:
        for f in fields:
            f.auto_now_add = True


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower().replace("'", "")).strip("_")


class Command(BaseCommand):
    help = "Deletes all non-superuser accounts and seeds 100 Tanzanian demo accounts with posts, reels, stories and chats."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42, help="Random seed (same seed, same data).")
        parser.add_argument(
            "--media-host", default=None,
            help="Public base URL of this server for the video clips when Supabase isn't configured "
                 "(default http://127.0.0.1:8000 with DJANGO_DEBUG=True).",
        )

    def handle(self, *args, **options):
        self.rng = random.Random(options["seed"])
        self.now = timezone.now()
        clips = self.publish_clips(options["media_host"])

        with transaction.atomic(), manual_timestamps():
            removed = self.flush()
            members = self.seed_users()
            self.seed_follows(members)
            posts = self.seed_posts(members, clips)
            self.seed_comments_and_likes(members, posts)
            self.seed_saves(members, posts)
            self.seed_stories(members, clips)
            reels = self.seed_reels(members, clips)
            self.seed_chats(members)

        business = [m.user.username for m in members if m.business]
        people = [m.user.username for m in members if not m.business]
        self.stdout.write(self.style.SUCCESS(
            f"\nRemoved {removed} old accounts. Seeded {len(members)} accounts "
            f"({len(business)} businesses), {len(posts)} posts and {len(reels)} reels.\n"
            f"Password for every seeded account: {PASSWORD}\n"
            f"Try a business: {', '.join(business[:3])}\n"
            f"Try a customer: {', '.join(people[:3])}"
        ))

    # -- Media ----------------------------------------------------------------

    def publish_clips(self, media_host):
        """Puts the bundled clips where the apps can stream them: {name: (video URL, poster URL)}."""
        names = [n for n in CLIPS if (CLIP_DIR / f"{n}.mp4").exists() and (CLIP_DIR / f"{n}.jpg").exists()]
        if not names:
            self.stdout.write(self.style.WARNING(f"No clips in {CLIP_DIR}: seeding without videos."))
            return {}

        use_supabase = storage.is_configured()
        if use_supabase and not storage.has_server_key():
            raise CommandError(storage.KEY_HELP)
        if not use_supabase:
            media_host = media_host or ("http://127.0.0.1:8000" if settings.DEBUG else None)
            if not media_host:
                # Local files on a production server would vanish on the next deploy.
                raise CommandError(
                    "The demo videos need public storage: set SUPABASE_URL and SUPABASE_SERVICE_KEY "
                    "(as in backend/.env), or pass --media-host <public URL of this server>."
                )
        self.stdout.write(f"Publishing {len(names)} video clips to {'Supabase' if use_supabase else media_host}...")

        urls = {}
        for name in names:
            pair = []
            for ext, content_type in (("mp4", "video/mp4"), ("jpg", "image/jpeg")):
                path = f"seed/{name}.{ext}"
                if use_supabase:
                    self.upload_once(path, (CLIP_DIR / f"{name}.{ext}").read_bytes(), content_type)
                    pair.append(storage.public_url(path))
                else:
                    if not default_storage.exists(path):
                        default_storage.save(path, ContentFile((CLIP_DIR / f"{name}.{ext}").read_bytes()))
                    pair.append(f"{media_host.rstrip('/')}{settings.MEDIA_URL.rstrip('/')}/{path}")
            urls[name] = tuple(pair)
        return urls

    def upload_once(self, path, data, content_type, attempts=4):
        """Uploads to Supabase unless an earlier run already did, retrying dropped connections."""
        for attempt in range(1, attempts + 1):
            try:
                if not storage.exists(path):
                    storage.upload(path, data, content_type)
                return
            except storage.StorageError:
                if storage.exists(path):  # the upload landed even though the reply got lost
                    return
                if attempt == attempts:
                    raise
                self.stdout.write(f"  upload of {path} failed, retrying ({attempt}/{attempts - 1})...")
                time.sleep(5 * attempt)

    # -- Helpers ----------------------------------------------------------------

    def ago(self, max_days, min_days=0.0):
        """A random moment between max_days and min_days ago, skewed towards recent."""
        days = min_days + (max_days - min_days) * self.rng.random() ** 1.5
        return self.now - timedelta(days=days)

    def after(self, moment, max_hours):
        return min(self.now, moment + timedelta(hours=self.rng.uniform(0.05, max_hours)))

    def pick_photo(self, member, used, exclude=()):
        """The least-used photo from the member's pools, never one they've already posted."""
        if member.own_photos:
            return member.own_photos.pop(0)
        pool = [p for key in member.pools for p in PHOTOS.get(key, [])]
        pool = [p for p in pool if p not in exclude] or pool
        least = min(used.get(p, 0) for p in pool)
        pid = self.rng.choice([p for p in pool if used.get(p, 0) == least])
        used[pid] = used.get(pid, 0) + 1
        return pid

    def weighted_sample(self, members, k, exclude=None):
        """k distinct members, popular accounts more likely."""
        chosen = {}
        candidates = [m for m in members if m is not exclude]
        weights = [m.popularity for m in candidates]
        k = min(k, len(candidates))
        while len(chosen) < k:
            m = self.rng.choices(candidates, weights)[0]
            chosen[m.user.pk] = m
        return list(chosen.values())

    # -- Accounts -------------------------------------------------------------

    def flush(self):
        old = User.objects.filter(is_superuser=False)
        count = old.count()
        self.stdout.write(f"Deleting {count} non-superuser accounts and everything they posted...")
        old.delete()
        Conversation.objects.filter(participants=None).delete()
        Hashtag.objects.filter(posts=None).delete()
        return count

    def seed_users(self):
        rng = self.rng
        men, women = list(MEN), list(WOMEN)
        rng.shuffle(men)
        rng.shuffle(women)
        names = {"m": iter(rng.sample(text.MEN_FIRST, len(text.MEN_FIRST))),
                 "f": iter(rng.sample(text.WOMEN_FIRST, len(text.WOMEN_FIRST)))}
        surnames = cycle(rng.sample(text.SURNAMES, len(text.SURNAMES)))
        faces = {"m": men, "f": women}
        password = make_password(PASSWORD)  # same password everywhere: hash it once
        categories = {}
        taken = set(User.objects.values_list("username", flat=True))

        def unique(name):
            name, n = name[:30], 2
            while name in taken:
                name, n = f"{name.rstrip('0123456789')}{n}", n + 1
            taken.add(name)
            return name

        specs = [(True, *b) for b in text.BUSINESSES] + [
            (False, None, gender, None, ["personal"], place, bio, None) for gender, place, bio in text.PEOPLE
        ]
        members, profiles = [], []
        for i, (is_business, display, gender, category, pools, place_key, bio, signature) in enumerate(specs):
            first, last = next(names[gender]), next(surnames)
            face = signature[0] if signature else faces[gender].pop()
            place = text.PLACES[place_key]
            joined = self.ago(420, 60)
            if is_business:
                full_name = display.format(first=first)
                username = unique(slug(full_name))
            else:
                full_name = f"{first} {last}"
                username = unique(slug(f"{first}{last}" if rng.random() < 0.6 else f"{first}_{last}"))
            verified = is_business and rng.random() < 0.18
            user = User(
                username=username, email=f"{username}@example.com", password=password,
                first_name=first, last_name=last, full_name=full_name, bio=bio, avatar_url=avatar(face),
                phone_number=f"+255700000{100 + i}" if is_business else "",
                is_business=is_business, is_verified=verified,
                is_private=not is_business and rng.random() < 0.25,
                date_joined=joined, created_at=joined,
                terms_accepted_at=joined, terms_version=settings.TERMS_VERSION,
            )
            popularity = rng.lognormvariate(0, 0.7) * (3 if verified else 1) * (1.6 if is_business else 1)
            member = Member(user, pools, place, is_business, popularity,
                            own_photos=list(signature[1]) if signature else [])
            members.append(member)
            if is_business:
                if category not in categories:
                    categories[category], _ = BusinessCategory.objects.get_or_create(
                        name=category, defaults={"icon": "store"})
                area, city, lat, lng = place
                profiles.append(BusinessProfile(
                    user=user, category=categories[category],
                    contact_phone=user.phone_number, contact_email=user.email, whatsapp_number=user.phone_number,
                    address=f"{area}, {city}", map_link=f"https://maps.google.com/?q={lat},{lng}",
                    latitude=lat, longitude=lng,
                    opening_hours={"mon_fri": "08:00 - 19:00", "sat": "09:00 - 17:00",
                                   "sun": rng.choice(["Closed", "10:00 - 15:00"])},
                ))

        User.objects.bulk_create([m.user for m in members], batch_size=BATCH)
        BusinessProfile.objects.bulk_create(profiles, batch_size=BATCH)
        self.stdout.write(f"Created {len(members)} accounts ({len(profiles)} businesses).")
        return members

    def seed_follows(self, members):
        rng = self.rng
        follows, notes = [], []
        for m in members:
            for target in self.weighted_sample(members, rng.randint(12, 40), exclude=m):
                pending = target.user.is_private and rng.random() < 0.35
                at = max(self.ago(150), m.user.created_at, target.user.created_at)
                follows.append(Follow(follower=m.user, following=target.user, created_at=at,
                                      status=Follow.PENDING if pending else Follow.ACCEPTED))
                if pending or at > self.now - timedelta(days=30):
                    notes.append(self.note(target.user, m.user, Notification.FOLLOW_REQUEST if pending
                                           else Notification.FOLLOW, at))
        Follow.objects.bulk_create(follows, batch_size=BATCH)
        Notification.objects.bulk_create(notes, batch_size=BATCH)
        self.followers = {}
        for f in follows:
            if f.status == Follow.ACCEPTED:
                self.followers.setdefault(f.following.pk, []).append(f.follower)
        self.stdout.write(f"Created {len(follows)} follows.")

    def note(self, recipient, actor, kind, at, **targets):
        return Notification(recipient=recipient, actor=actor, notification_type=kind, created_at=at,
                            is_read=at < self.now - timedelta(days=2), **targets)

    # -- Posts ------------------------------------------------------------------

    def seed_posts(self, members, clips):
        rng = self.rng
        clips_by_pool = {}
        for name, (pools, _, _) in CLIPS.items():
            if name in clips:
                for pool in pools:
                    clips_by_pool.setdefault(pool, []).append(name)
        used_photos, used_clips = {}, {}
        posts, media, tags, tagged = [], [], [], []
        tag_names = set()

        for m in members:
            count = rng.randint(3, 6) if m.business else rng.randint(1, 3)
            count = max(count, len(m.own_photos))
            area, city, lat, lng = m.place
            for _ in range(count):
                pool = rng.choice(m.pools)
                created = max(self.ago(120), m.user.created_at)
                post = Post(author=m.user, created_at=created,
                            caption=rng.choice(text.CAPTIONS[pool]).format(area=area, city=city),
                            comments_disabled=rng.random() < 0.03, like_count_hidden=rng.random() < 0.04)
                if rng.random() < 0.75:
                    post.location_name = f"{area}, {city}"
                    post.latitude, post.longitude = lat, lng

                # Video posts, each clip on at most two posts so the feed doesn't repeat itself.
                options = [c for p in m.pools for c in clips_by_pool.get(p, []) if used_clips.get(c, 0) < 2]
                if options and not m.own_photos and rng.random() < 0.25:
                    least = min(used_clips.get(c, 0) for c in options)
                    name = rng.choice([c for c in options if used_clips.get(c, 0) == least])
                    used_clips[name] = used_clips.get(name, 0) + 1
                    post.location_name = CLIPS[name][1]
                    if rng.random() < 0.5:
                        post.caption = CLIPS[name][2]
                    media.append(PostMedia(post=post, media_type=PostMedia.VIDEO, file_url=clips[name][0], order=0))
                else:
                    shown = []
                    for order in range(rng.choice([1, 1, 1, 1, 2, 3])):
                        pid = self.pick_photo(m, used_photos, exclude=shown + m.posts)
                        shown.append(pid)
                        media.append(PostMedia(post=post, media_type=PostMedia.IMAGE,
                                               file_url=post_image(pid), order=order))
                    m.posts.extend(shown)

                # The apps show a post's hashtags under the caption, so they stay out of the caption text.
                chosen = rng.sample(text.HASHTAGS[pool], rng.randint(1, 3))
                if rng.random() < 0.6:
                    chosen.append(rng.choice(text.COMMON_TAGS))
                tags.append((post, set(chosen)))
                tag_names.update(chosen)
                if rng.random() < 0.06:
                    for friend in self.weighted_sample(members, rng.randint(1, 2), exclude=m):
                        tagged.append((post, friend.user))
                post.member = m
                posts.append(post)

        Post.objects.bulk_create(posts, batch_size=BATCH)
        PostMedia.objects.bulk_create(media, batch_size=BATCH)
        Hashtag.objects.bulk_create([Hashtag(name=n) for n in tag_names], ignore_conflicts=True)
        tag_ids = dict(Hashtag.objects.filter(name__in=tag_names).values_list("name", "id"))
        Post.hashtags.through.objects.bulk_create(
            [Post.hashtags.through(post_id=p.pk, hashtag_id=tag_ids[n]) for p, names in tags for n in names],
            batch_size=BATCH)
        Post.tagged_users.through.objects.bulk_create(
            [Post.tagged_users.through(post_id=p.pk, user_id=u.pk) for p, u in tagged],
            batch_size=BATCH, ignore_conflicts=True)
        Notification.objects.bulk_create(
            [self.note(u, p.author, Notification.TAG, p.created_at, post=p) for p, u in tagged], batch_size=BATCH)
        videos = sum(1 for x in media if x.media_type == PostMedia.VIDEO)
        self.stdout.write(f"Created {len(posts)} posts ({videos} videos, {len(media) - videos} photos).")
        return posts

    def audience(self, members, author, k):
        """Mostly the author's followers, plus a few people who found the post on Explore."""
        fans = self.followers.get(author.user.pk, [])
        picked = {u.pk: u for u in self.rng.sample(fans, min(len(fans), int(k * 0.8)))}
        for m in self.weighted_sample(members, k - len(picked), exclude=author):
            picked.setdefault(m.user.pk, m.user)
        return list(picked.values())

    def seed_comments_and_likes(self, members, posts):
        rng = self.rng
        comments, likes, notes = [], [], []
        for post in posts:
            author, owner = post.member, post.author
            area, city, _, _ = author.place
            if not post.comments_disabled:
                for user in self.audience(members, author, rng.randint(0, int(3 + author.popularity * 3))):
                    at = self.after(post.created_at, 72)
                    question, answers = rng.choice(text.QUESTIONS)
                    asks = author.business and rng.random() < 0.35
                    c = Comment(post=post, author=user, created_at=at,
                                text=question if asks else rng.choice(text.COMMENTS))
                    comments.append(c)
                    notes.append(self.note(owner, user, Notification.COMMENT, at, post=post, comment=c))
                    if asks or rng.random() < 0.3:
                        # The owner answers on their own post.
                        reply_at = self.after(at, 12)
                        r = Comment(post=post, author=owner, parent=c, created_at=reply_at,
                                    text=rng.choice(answers if asks else text.OWNER_REPLIES).format(area=area, city=city))
                        comments.append(r)
                        notes.append(self.note(user, owner, Notification.COMMENT, reply_at, post=post, comment=r))
                    elif rng.random() < 0.2:
                        friend = rng.choice(members).user
                        if friend != user:
                            reply_at = self.after(at, 24)
                            r = Comment(post=post, author=friend, parent=c, created_at=reply_at,
                                        text=rng.choice(text.FRIEND_REPLIES))
                            comments.append(r)
                            notes.append(self.note(user, friend, Notification.COMMENT, reply_at, post=post, comment=r))

            for user in self.audience(members, author, rng.randint(2, int(8 + author.popularity * 14))):
                at = self.after(post.created_at, 96)
                likes.append(Like(user=user, post=post, created_at=at))
                if at > self.now - timedelta(days=14) and rng.random() < 0.5:
                    notes.append(self.note(owner, user, Notification.LIKE, at, post=post))

        for c in comments:
            for user in rng.sample(members, rng.choice([0, 0, 0, 1, 1, 2, 4])):
                if user.user != c.author:
                    likes.append(Like(user=user.user, comment=c, created_at=self.after(c.created_at, 24)))

        # Top-level comments first: replies point at them.
        Comment.objects.bulk_create([c for c in comments if c.parent is None], batch_size=BATCH)
        Comment.objects.bulk_create([c for c in comments if c.parent is not None], batch_size=BATCH)
        Like.objects.bulk_create(likes, batch_size=BATCH, ignore_conflicts=True)
        Notification.objects.bulk_create([n for n in notes if n.actor_id != n.recipient_id], batch_size=BATCH)
        replies = sum(1 for c in comments if c.parent is not None)
        self.stdout.write(f"Created {len(comments)} comments ({replies} replies) and {len(likes)} likes.")

    def seed_saves(self, members, posts):
        rng = self.rng
        saves = []
        for m in rng.sample(members, 60):
            collection = rng.choice(["All Posts", "All Posts", "Ideas", "Shopping", "Food spots", "Trips"])
            for post in rng.sample(posts, rng.randint(2, 10)):
                if post.author != m.user:
                    saves.append(SavedPost(user=m.user, post=post, collection_name=collection,
                                           created_at=self.after(post.created_at, 48)))
        SavedPost.objects.bulk_create(saves, batch_size=BATCH, ignore_conflicts=True)
        self.stdout.write(f"Created {len(saves)} saved posts.")

    # -- Stories, highlights, reels ------------------------------------------------

    def story_media(self, m, clips, used):
        """(media_type, file URL, cover URL) for one story."""
        options = [n for n, (pools, _, _) in CLIPS.items() if n in clips and set(pools) & set(m.pools)]
        if options and self.rng.random() < 0.25:
            video, poster = clips[self.rng.choice(options)]
            return Story.VIDEO, video, poster
        pid = self.pick_photo(Member(m.user, m.pools, m.place, m.business, 0), used)
        return Story.IMAGE, story_image(pid), photo(pid, 400, 400)

    def seed_stories(self, members, clips):
        rng = self.rng
        stories, stickers, views, highlights, links = [], [], [], [], []
        used = {}
        for m in members:
            fans = self.followers.get(m.user.pk, [])
            if rng.random() < 0.5:  # posted today: shows in the stories bar
                for _ in range(rng.randint(1, 4)):
                    kind, url, _ = self.story_media(m, clips, used)
                    at = self.now - timedelta(hours=rng.uniform(0.2, 22))
                    s = Story(author=m.user, media_type=kind, file_url=url, created_at=at,
                              expires_at=at + timedelta(hours=24), caption=rng.choice(text.STORY_CAPTIONS))
                    stories.append(s)
                    if rng.random() < 0.15:
                        question, opts = rng.choice(text.POLLS)
                        stickers.append(StorySticker(story=s, sticker_type=StorySticker.POLL,
                                                     data={"question": question, "options": opts}))
                    for viewer in rng.sample(fans, min(len(fans), rng.randint(3, 25))):
                        views.append(StoryView(story=s, viewer=viewer, viewed_at=self.after(at, 6)))
            if m.business and rng.random() < 0.6:  # older stories kept as profile highlights
                for title in rng.sample(text.HIGHLIGHT_TITLES, rng.randint(1, 3)):
                    saved, cover = [], ""
                    for _ in range(rng.randint(2, 4)):
                        kind, url, thumb = self.story_media(m, clips, used)
                        at = self.ago(90, 3)
                        saved.append(Story(author=m.user, media_type=kind, file_url=url, created_at=at,
                                           expires_at=at + timedelta(hours=24)))
                        cover = cover or thumb
                    stories.extend(saved)
                    h = Highlight(owner=m.user, title=title, cover_url=cover, created_at=saved[-1].created_at)
                    highlights.append(h)
                    links.extend((h, s) for s in saved)

        Story.objects.bulk_create(stories, batch_size=BATCH)
        StorySticker.objects.bulk_create(stickers, batch_size=BATCH)
        StoryView.objects.bulk_create(views, batch_size=BATCH, ignore_conflicts=True)
        Highlight.objects.bulk_create(highlights, batch_size=BATCH)
        Highlight.stories.through.objects.bulk_create(
            [Highlight.stories.through(highlight_id=h.pk, story_id=s.pk) for h, s in links], batch_size=BATCH)
        live = sum(1 for s in stories if s.expires_at > self.now)
        self.stdout.write(f"Created {live} live stories and {len(highlights)} highlights.")

    def seed_reels(self, members, clips):
        rng = self.rng
        reels, comments, likes, notes = [], [], [], []
        uses = {}
        for m in members:
            options = [n for n, (pools, _, _) in CLIPS.items() if n in clips and set(pools) & set(m.pools)]
            if not options or rng.random() < (0.25 if m.business else 0.7):
                continue
            for name in rng.sample(options, min(len(options), rng.randint(1, 2))):
                if uses.get(name, 0) >= 3:
                    continue
                uses[name] = uses.get(name, 0) + 1
                video, poster = clips[name]
                at = max(self.ago(60), m.user.created_at)
                reel = Reel(author=m.user, video_url=video, thumbnail_url=poster, created_at=at,
                            caption=f"{CLIPS[name][2]}\n\n#{rng.choice(text.HASHTAGS[rng.choice(m.pools)])} #tanzania",
                            audio_title=f"{rng.choice(text.AUDIO)} - {m.user.username}",
                            view_count=int(rng.lognormvariate(7, 1.2)), share_count=rng.randint(0, 300))
                reels.append(reel)
                for user in self.audience(members, m, rng.randint(0, 8)):
                    c_at = self.after(at, 48)
                    comments.append(ReelComment(reel=reel, author=user, created_at=c_at,
                                                text=rng.choice(text.COMMENTS)))
                for user in self.audience(members, m, rng.randint(5, int(15 + m.popularity * 20))):
                    l_at = self.after(at, 96)
                    likes.append(Like(user=user, reel=reel, created_at=l_at))
                    if l_at > self.now - timedelta(days=7) and rng.random() < 0.3:
                        notes.append(self.note(m.user, user, Notification.LIKE, l_at, reel=reel))
        Reel.objects.bulk_create(reels, batch_size=BATCH)
        ReelComment.objects.bulk_create(comments, batch_size=BATCH)
        Like.objects.bulk_create(likes, batch_size=BATCH, ignore_conflicts=True)
        Notification.objects.bulk_create([n for n in notes if n.actor_id != n.recipient_id], batch_size=BATCH)
        self.stdout.write(f"Created {len(reels)} reels with {len(comments)} comments and {len(likes)} likes.")
        return reels

    # -- Chats ----------------------------------------------------------------

    def seed_chats(self, members):
        rng = self.rng
        businesses = [m for m in members if m.business]
        convos, messages, members_of, reads = [], [], [], []

        def thread(convo, people, lines, start):
            at = start
            for i, line in enumerate(lines):
                sender = people[i % len(people)] if len(people) == 2 else rng.choice(people)
                at = self.after(at, 3)
                msg = Message(conversation=convo, sender=sender, text=line, created_at=at)
                messages.append(msg)
                last = i == len(lines) - 1
                # Everything is read except, sometimes, the newest message.
                for p in people:
                    if p == sender or not last or rng.random() < 0.5:
                        reads.append((msg, p))

        pairs = set()
        for _ in range(90):
            customer = rng.choice(members)
            shop = rng.choice(businesses)
            key = frozenset((customer.user.pk, shop.user.pk))
            if customer is shop or key in pairs:
                continue
            pairs.add(key)
            start = self.ago(45)
            convo = Conversation(created_at=start)
            convos.append(convo)
            members_of.extend((convo, u) for u in (customer.user, shop.user))
            script = rng.choice([lines for pools, lines in text.CHATS if pools is None or set(pools) & set(shop.pools)])
            thread(convo, [customer.user, shop.user],
                   [line.format(business=shop.user.full_name) for line in script], start)

        for name, lines in text.GROUPS:
            people = [m.user for m in rng.sample(members, rng.randint(4, 8))]
            start = self.ago(30)
            convo = Conversation(is_group=True, group_name=name, created_at=start)
            convos.append(convo)
            members_of.extend((convo, u) for u in people)
            thread(convo, people, lines, start)

        Conversation.objects.bulk_create(convos, batch_size=BATCH)
        Conversation.participants.through.objects.bulk_create(
            [Conversation.participants.through(conversation_id=c.pk, user_id=u.pk) for c, u in members_of],
            batch_size=BATCH)
        Message.objects.bulk_create(messages, batch_size=BATCH)
        Message.read_by.through.objects.bulk_create(
            [Message.read_by.through(message_id=m.pk, user_id=u.pk) for m, u in reads], batch_size=BATCH)
        self.stdout.write(f"Created {len(convos)} chats with {len(messages)} messages.")
