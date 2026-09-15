import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user = the Nepo profile itself (personal or business)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150, blank=True)
    bio = models.CharField(max_length=250, blank=True)
    avatar_url = models.URLField(blank=True, help_text="Supabase Storage public URL")
    website = models.URLField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    is_private = models.BooleanField(default=False)
    is_business = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def followers_count(self):
        return self.followers.filter(status="accepted").count()

    @property
    def following_count(self):
        return self.following.filter(status="accepted").count()

    @property
    def posts_count(self):
        return self.posts.count()

    def __str__(self):
        return self.username


class Highlight(models.Model):
    """A saved-stories highlight shown on the profile grid."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, related_name="highlights", on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    cover_url = models.URLField(blank=True)
    stories = models.ManyToManyField("content.Story", related_name="highlights", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.owner.username} - {self.title}"
