"""
Seeds Nepo with a realistic, richly-connected demo dataset: business
categories, ~35 users (personal + business) with follow relationships,
posts with images/videos/hashtags, comments, likes, stories, reels,
highlights, saved posts, notifications, and DM conversations.

Run with:  python manage.py seed_data
Add --no-flush to keep existing data instead of wiping non-superusers first.

The goal is that anyone who registers a brand-new account on Nepo
immediately lands in a "populated" app: people to follow, a feed once
they follow a few, an Explore grid, Reels to watch, and a couple of
categories of businesses to discover.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from business.models import BusinessCategory, BusinessProfile
from content.models import (
    Comment, Hashtag, Like, Post, PostMedia, Reel, ReelComment,
    SavedPost, Story, StorySticker, StoryView,
)
from social.models import Conversation, Follow, Message, Notification

User = get_user_model()

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

TANZANIAN_CITIES = [
    "Dar es Salaam", "Mbeya", "Arusha", "Dodoma", "Mwanza", "Zanzibar City",
    "Moshi", "Morogoro", "Tanga", "Iringa",
]

BUSINESS_CATEGORIES = [
    ("Restaurant & Food", "utensils"),
    ("Fashion & Retail", "shirt"),
    ("Beauty & Wellness", "sparkles"),
    ("Electronics & Tech", "smartphone"),
    ("Agriculture", "wheat"),
    ("Photography & Media", "camera"),
    ("Real Estate", "home"),
    ("Transport & Logistics", "truck"),
    ("Coffee & Bakery", "coffee"),
    ("Fitness & Sports", "dumbbell"),
]

NAMES = [
    ("Amani", "Mrema"), ("Zawadi", "Mushi"), ("Baraka", "Kileo"),
    ("Neema", "Komba"), ("Juma", "Mwakalinga"), ("Fatuma", "Ally"),
    ("Hamisi", "Ngowi"), ("Furaha", "Shirima"), ("Rehema", "Massawe"),
    ("Emmanuel", "Lyimo"), ("Grace", "Temba"), ("Salum", "Kessy"),
    ("Happiness", "Mollel"), ("Iddi", "Chacha"), ("Winnie", "Mapunda"),
    ("Godfrey", "Sanga"), ("Aisha", "Mbwana"), ("Daudi", "Mrisho"),
    ("Consolata", "Kimario"), ("Yusuf", "Haule"),
    ("Brooklyn", "Simmons"), ("Sienna", "Miller"), ("Esther", "Howard"),
    ("Haris", "Ahmed"), ("Abdullah", "Khan"), ("Alex", "Johnson"),
    ("Jordan", "Lee"), ("Taylor", "Smith"), ("Morgan", "Freeman"),
    ("Casey", "Neistat"), ("Riley", "Reid"), ("Jamie", "Oliver"),
    ("Quinn", "Fabray"), ("Avery", "Bradley"), ("Parker", "Posey"),
]

BUSINESS_BIOS = [
    "Serving the freshest flavors in town 🍲 Order online or visit us today.",
    "Handmade fashion, made in Tanzania 🇹🇿 DM to order.",
    "Your one-stop shop for phones & accessories 📱 Warranty on everything.",
    "Fresh produce straight from the farm to your table 🌾",
    "Capturing your best moments 📸 Weddings · Events · Portraits",
    "Quality you can trust. Family-owned since day one.",
    "Book your appointment today — glow starts here ✨",
    "Fast, reliable delivery across the region 🚚",
]

PERSONAL_BIOS = [
    "Just here sharing the journey ✨",
    "Coffee first, everything else after ☕",
    "Building something new every day.",
    "Traveler. Dreamer. Doer.",
    "Living life one post at a time 🌍",
    "Small joys, big gratitude 🙏",
    "Football, food, and good company.",
    "",
    "",
]

POST_CAPTIONS = [
    "New drop just landed — come check it out! 🔥",
    "Grateful for another beautiful day in {city} 🌅",
    "Behind the scenes at the shop today 👀",
    "Can't believe how far we've come this year.",
    "Fresh batch, hot and ready 😋",
    "Weekend vibes with the team 🙌",
    "Nothing beats {city} sunsets.",
    "Customer favorite, back in stock!",
    "Small business, big dreams 💪",
    "Quality over quantity, always.",
    "Just wrapped up an amazing project.",
    "Thank you {city} for the love and support ❤️",
    "New menu items you have to try.",
    "Proudly made in Tanzania 🇹🇿",
    "Another satisfied customer today!",
]

HASHTAG_POOL = [
    "tanzania", "madeintanzania", "dar", "mbeya", "arusha", "smallbusiness",
    "business254", "eastafrica", "foodie", "fashion", "entrepreneur",
    "localbusiness", "supportlocal", "swahili", "hustle",
]

COMMENT_TEXTS = [
    "This is amazing! 🔥", "Love this so much ❤️", "Where can I order?",
    "🙌🙌🙌", "So proud of you!", "Beautiful 😍", "Need this in my life",
    "Great work as always", "How much is this?", "Congratulations! 🎉",
    "Following for more of this content", "This made my day 😊",
    "Absolutely stunning", "Keep it up!", "Can you deliver to Mbeya?",
]

REEL_CAPTIONS = [
    "Quick look at how it's made 🎬", "A day in the life of a small business owner",
    "Behind the counter today 👨‍🍳", "This trick changed everything",
    "POV: opening shop on a Monday", "Wait for it... 😂",
    "Our process from start to finish", "Rate this out of 10",
]

AUDIO_TITLES = [
    "Original audio - nepo_user", "Trending sound - Afrobeat mix",
    "Original audio - dailyvibes", "Trending sound - Bongo Flava hit",
    "Original audio - studio session",
]

# Public-domain / Creative-Commons sample videos (Blender Foundation open
# movies, distributed via Google's public sample-video bucket) used purely
# as placeholder reel content in this demo environment.
SAMPLE_VIDEOS = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
]

MESSAGE_OPENERS = [
    "Hey! Loved your last post 👋", "Hi, is this still available?",
    "Thanks for the follow!", "Quick question about your shop hours.",
    "Can we collab sometime?", "Just placed an order, excited!",
]
MESSAGE_REPLIES = [
    "Hey, thank you so much! 🙏", "Yes it is, want me to hold one for you?",
    "Of course, anytime!", "We're open 9am-7pm every day.",
    "I'd love that, let's talk details.", "Awesome, thank you for your support!",
]


def avatar_for(index: int) -> str:
    # pravatar.cc has a fixed set of ~70 real-photo avatars, good for demo data.
    return f"https://i.pravatar.cc/300?img={(index % 70) + 1}"


def picsum(seed: str, w: int, h: int) -> str:
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


class Command(BaseCommand):
    help = "Seeds Nepo with a full demo dataset: users, follows, posts, reels, stories, DMs, and more."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-flush", action="store_true",
            help="Do not delete existing non-superuser data before seeding.",
        )

    def handle(self, *args, **options):
        random.seed(42)

        if not options["no_flush"]:
            self.stdout.write("Flushing existing demo data...")
            User.objects.filter(is_superuser=False).delete()
            Hashtag.objects.all().delete()
            BusinessCategory.objects.all().delete()

        with transaction.atomic():
            categories = self.seed_categories()
            users = self.seed_users(categories)
            self.seed_follows(users)
            posts = self.seed_posts(users)
            self.seed_comments_and_likes(users, posts)
            self.seed_stories_and_highlights(users)
            reels = self.seed_reels(users)
            self.seed_reel_comments_and_likes(users, reels)
            self.seed_saved_posts(users, posts)
            self.seed_conversations(users)

        self.stdout.write(self.style.SUCCESS(
            f"\nSeeded {len(users)} users, {len(posts)} posts, {len(reels)} reels, "
            f"plus stories, comments, likes, follows, and DMs.\n"
            f"Every seeded account's password is: password123\n"
            f"Example login: username '{users[0].username}', password 'password123'"
        ))

    # -- Categories -----------------------------------------------------------

    def seed_categories(self):
        cats = []
        for name, icon in BUSINESS_CATEGORIES:
            cat, _ = BusinessCategory.objects.get_or_create(name=name, defaults={"icon": icon})
            cats.append(cat)
        self.stdout.write(f"Seeded {len(cats)} business categories.")
        return cats

    # -- Users + business profiles ---------------------------------------------

    def seed_users(self, categories):
        users = []
        for i, (first, last) in enumerate(NAMES):
            username = f"{first.lower()}{last.lower()}"
            is_business = random.random() < 0.4
            is_verified = random.random() < 0.2
            is_private = (not is_business) and random.random() < 0.15

            user = User(
                username=username,
                email=f"{username}@example.com",
                full_name=f"{first} {last}",
                bio=random.choice(BUSINESS_BIOS if is_business else PERSONAL_BIOS),
                avatar_url=avatar_for(i),
                website=f"{username}.co.tz" if is_business and random.random() < 0.6 else "",
                phone_number=f"+2557{random.randint(10000000, 99999999)}",
                is_private=is_private,
                is_business=is_business,
                is_verified=is_verified,
            )
            user.set_password("password123")
            user.save()
            users.append(user)

            if is_business:
                BusinessProfile.objects.create(
                    user=user,
                    category=random.choice(categories),
                    contact_phone=user.phone_number,
                    contact_email=user.email,
                    whatsapp_number=user.phone_number,
                    address=f"{random.choice(['Kariakoo', 'Sinza', 'Mbezi', 'Uyole', 'CBD', 'Msasani'])}, "
                            f"{random.choice(TANZANIAN_CITIES)}",
                    map_link="https://maps.google.com",
                    latitude=round(random.uniform(-11.0, -1.0), 5),
                    longitude=round(random.uniform(29.5, 40.0), 5),
                    opening_hours={
                        "mon_fri": "08:00-19:00",
                        "sat": "09:00-17:00",
                        "sun": "Closed",
                    },
                )

        self.stdout.write(f"Seeded {len(users)} users ({sum(u.is_business for u in users)} business).")
        return users

    # -- Social graph -----------------------------------------------------------

    def seed_follows(self, users):
        count = 0
        for user in users:
            others = [u for u in users if u != user]
            num_follows = random.randint(6, min(18, len(others)))
            for target in random.sample(others, num_follows):
                follow, created = Follow.objects.get_or_create(follower=user, following=target)
                if created:
                    count += 1
                    notif_type = "follow" if follow.status == Follow.ACCEPTED else "follow_request"
                    Notification.objects.create(recipient=target, actor=user, notification_type=notif_type)
        self.stdout.write(f"Seeded {count} follow relationships.")

    # -- Posts --------------------------------------------------------------

    def seed_posts(self, users):
        posts = []
        seed_counter = 0
        for user in users:
            num_posts = random.randint(2, 6)
            for _ in range(num_posts):
                seed_counter += 1
                city = random.choice(TANZANIAN_CITIES)
                caption = random.choice(POST_CAPTIONS).format(city=city)
                post = Post.objects.create(
                    author=user,
                    caption=caption,
                    location_name=city if random.random() < 0.7 else "",
                    comments_disabled=random.random() < 0.03,
                )
                num_media = random.choice([1, 1, 1, 2, 3])
                for order in range(num_media):
                    is_video = random.random() < 0.12
                    seed = f"post{seed_counter}-{order}"
                    if is_video:
                        PostMedia.objects.create(
                            post=post, media_type="video",
                            file_url=random.choice(SAMPLE_VIDEOS), order=order,
                        )
                    else:
                        PostMedia.objects.create(
                            post=post, media_type="image",
                            file_url=picsum(seed, 800, 800), order=order,
                        )
                for tag_name in random.sample(HASHTAG_POOL, random.randint(0, 3)):
                    tag, _ = Hashtag.objects.get_or_create(name=tag_name)
                    post.hashtags.add(tag)
                posts.append(post)
        self.stdout.write(f"Seeded {len(posts)} posts.")
        return posts

    # -- Comments + likes -----------------------------------------------------

    def seed_comments_and_likes(self, users, posts):
        comment_count = 0
        like_count = 0
        for post in posts:
            if not post.comments_disabled:
                for _ in range(random.randint(0, 5)):
                    commenter = random.choice(users)
                    comment = Comment.objects.create(
                        post=post, author=commenter, text=random.choice(COMMENT_TEXTS),
                    )
                    comment_count += 1
                    if post.author != commenter:
                        Notification.objects.create(
                            recipient=post.author, actor=commenter,
                            notification_type="comment", post=post, comment=comment,
                        )
                    if random.random() < 0.25:
                        replier = random.choice(users)
                        Comment.objects.create(
                            post=post, author=replier, parent=comment,
                            text=random.choice(COMMENT_TEXTS),
                        )
                        comment_count += 1

            likers = random.sample(users, random.randint(0, min(15, len(users))))
            for liker in likers:
                _, created = Like.objects.get_or_create(user=liker, post=post)
                if created:
                    like_count += 1
                    if post.author != liker and random.random() < 0.3:
                        Notification.objects.create(
                            recipient=post.author, actor=liker,
                            notification_type="like", post=post,
                        )
        self.stdout.write(f"Seeded {comment_count} comments and {like_count} post likes.")

    # -- Stories + highlights ---------------------------------------------------

    def seed_stories_and_highlights(self, users):
        story_count = 0
        active_authors = random.sample(users, min(20, len(users)))
        for user in active_authors:
            user_stories = []
            for _ in range(random.randint(1, 3)):
                is_video = random.random() < 0.15
                story = Story.objects.create(
                    author=user,
                    media_type="video" if is_video else "image",
                    file_url=random.choice(SAMPLE_VIDEOS) if is_video else picsum(f"story{story_count}", 720, 1280),
                    caption=random.choice(["", "", "Ask me anything!", "New arrivals 👀", ""]),
                    expires_at=timezone.now() + timedelta(hours=random.randint(4, 24)),
                )
                story_count += 1
                user_stories.append(story)
                if random.random() < 0.2:
                    StorySticker.objects.create(
                        story=story, sticker_type=StorySticker.POLL,
                        data={"question": "Which one do you prefer?", "options": ["Option A", "Option B"]},
                    )
                for viewer in random.sample(users, random.randint(0, 8)):
                    if viewer != user:
                        StoryView.objects.get_or_create(story=story, viewer=viewer)

            if user_stories and random.random() < 0.4:
                from accounts.models import Highlight
                highlight = Highlight.objects.create(
                    owner=user,
                    title=random.choice(["Highlights", "New In", "Reviews", "Behind the Scenes"]),
                    cover_url=user_stories[0].file_url if user_stories[0].media_type == "image" else user.avatar_url,
                )
                highlight.stories.set(user_stories)

        self.stdout.write(f"Seeded {story_count} stories across {len(active_authors)} users.")

    # -- Reels --------------------------------------------------------------

    def seed_reels(self, users):
        reels = []
        reel_authors = random.sample(users, min(20, len(users)))
        for user in reel_authors:
            for _ in range(random.randint(1, 2)):
                reel = Reel.objects.create(
                    author=user,
                    video_url=random.choice(SAMPLE_VIDEOS),
                    thumbnail_url=picsum(f"reel{len(reels)}", 720, 1280),
                    caption=random.choice(REEL_CAPTIONS),
                    audio_title=random.choice(AUDIO_TITLES),
                    view_count=random.randint(50, 25000),
                    share_count=random.randint(0, 500),
                )
                reels.append(reel)
        self.stdout.write(f"Seeded {len(reels)} reels.")
        return reels

    def seed_reel_comments_and_likes(self, users, reels):
        comment_count = 0
        like_count = 0
        for reel in reels:
            for _ in range(random.randint(0, 4)):
                ReelComment.objects.create(
                    reel=reel, author=random.choice(users), text=random.choice(COMMENT_TEXTS),
                )
                comment_count += 1
            for liker in random.sample(users, random.randint(0, min(12, len(users)))):
                _, created = Like.objects.get_or_create(user=liker, reel=reel)
                if created:
                    like_count += 1
        self.stdout.write(f"Seeded {comment_count} reel comments and {like_count} reel likes.")

    # -- Saved posts ----------------------------------------------------------

    def seed_saved_posts(self, users, posts):
        count = 0
        for user in random.sample(users, min(15, len(users))):
            for post in random.sample(posts, random.randint(1, 5)):
                _, created = SavedPost.objects.get_or_create(user=user, post=post)
                if created:
                    count += 1
        self.stdout.write(f"Seeded {count} saved posts.")

    # -- Conversations + messages -----------------------------------------------

    def seed_conversations(self, users):
        count = 0
        pairs = set()
        for _ in range(15):
            a, b = random.sample(users, 2)
            key = tuple(sorted([str(a.id), str(b.id)]))
            if key in pairs:
                continue
            pairs.add(key)
            convo = Conversation.objects.create()
            convo.participants.set([a, b])
            Message.objects.create(conversation=convo, sender=a, kind="text", text=random.choice(MESSAGE_OPENERS))
            if random.random() < 0.8:
                Message.objects.create(conversation=convo, sender=b, kind="text", text=random.choice(MESSAGE_REPLIES))
            count += 1
        self.stdout.write(f"Seeded {count} conversations with messages.")
