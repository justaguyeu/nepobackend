import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from content.models import Post, PostMedia, Story

User = get_user_model()

NAMES = [
    ("Brooklyn", "Simmons"), ("Sienna", "Miller"), ("Esther", "Howard"),
    ("Haris", "Ahmed"), ("Abdullah", "Khan"), ("Alex", "Johnson"),
    ("Jordan", "Lee"), ("Taylor", "Smith"), ("Morgan", "Freeman"),
    ("Casey", "Neistat"), ("Riley", "Reid"), ("Jamie", "Oliver"),
    ("Quinn", "Fabray"), ("Peyton", "Manning"), ("Skyler", "White"),
    ("Avery", "Bradley"), ("Cameron", "Diaz"), ("Parker", "Posey"),
    ("Blake", "Lively"), ("Finley", "Craig")
]

class Command(BaseCommand):
    help = 'Seeds the database with 20 users and their posts/stories.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting to seed database...")

        # Optional: Delete existing users for a clean slate
        # User.objects.exclude(is_superuser=True).delete()
        # Post.objects.all().delete()
        # Story.objects.all().delete()

        created_users = []
        for first, last in NAMES:
            username = f"{first.lower()}{last.lower()}{random.randint(10, 99)}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'full_name': f"{first} {last}",
                    'bio': '🔥 Top UI/UX Inspiration\n🔥 Best resources and guide',
                    'avatar_url': f"https://picsum.photos/150/150?random={random.randint(1, 1000)}",
                    'is_business': random.choice([True, False]),
                    'is_verified': random.choice([True, False, False]),
                }
            )
            if created:
                user.set_password('password123')
                user.save()
            created_users.append(user)
        
        self.stdout.write(f"Created/found {len(created_users)} users.")

        captions = [
            "More fresh new travel content Inso for all you travel bloggers or creators working but as ...",
            "Loving the vibes today! 🌞✨",
            "Just another day in paradise.",
            "Can't believe I finally made it here! #travel #goals",
            "UI/UX inspiration of the day.",
        ]

        # Seed Posts
        for user in created_users:
            num_posts = random.randint(1, 3)
            for _ in range(num_posts):
                post = Post.objects.create(
                    author=user,
                    caption=random.choice(captions),
                    location_name=random.choice(["New York", "London", "Paris", "Tokyo", "Bali", ""]),
                )
                PostMedia.objects.create(
                    post=post,
                    media_type="image",
                    file_url=f"https://picsum.photos/400/450?random={random.randint(1, 5000)}",
                    order=0
                )
        
        self.stdout.write("Created posts.")

        # Seed Stories (for about half the users)
        for user in random.sample(created_users, 10):
            Story.objects.create(
                author=user,
                media_type="image",
                file_url=f"https://picsum.photos/400/700?random={random.randint(1, 5000)}",
                expires_at=timezone.now() + timedelta(hours=24)
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded database.'))
