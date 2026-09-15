import uuid
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Hashtag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return f"#{self.name}"


class Post(models.Model):
    """A feed post: single image or multi-image carousel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, related_name="posts", on_delete=models.CASCADE)
    caption = models.TextField(blank=True)
    location_name = models.CharField(max_length=150, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    hashtags = models.ManyToManyField(Hashtag, related_name="posts", blank=True)
    tagged_users = models.ManyToManyField(User, related_name="tagged_in_posts", blank=True)
    comments_disabled = models.BooleanField(default=False)
    like_count_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.count()

    def __str__(self):
        return f"Post({self.id}) by {self.author}"


class PostMedia(models.Model):
    """One image/video within a post's carousel."""

    IMAGE, VIDEO = "image", "video"
    MEDIA_TYPES = [(IMAGE, "Image"), (VIDEO, "Video")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, related_name="media", on_delete=models.CASCADE)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES, default=IMAGE)
    file_url = models.URLField(help_text="Supabase Storage public URL")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(User, related_name="comments", on_delete=models.CASCADE)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="replies", on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def like_count(self):
        return self.likes.count()


class Like(models.Model):
    """Generic-ish like: exactly one of post/comment/reel is set."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, related_name="likes", on_delete=models.CASCADE)
    post = models.ForeignKey(Post, null=True, blank=True, related_name="likes", on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, null=True, blank=True, related_name="likes", on_delete=models.CASCADE)
    reel = models.ForeignKey("Reel", null=True, blank=True, related_name="likes", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="unique_post_like"),
            models.UniqueConstraint(fields=["user", "comment"], name="unique_comment_like"),
            models.UniqueConstraint(fields=["user", "reel"], name="unique_reel_like"),
        ]


class SavedPost(models.Model):
    """A post saved into one of the user's private collections."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, related_name="saved_posts", on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name="saved_by", on_delete=models.CASCADE)
    collection_name = models.CharField(max_length=100, default="All Posts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "post", "collection_name")


class Story(models.Model):
    """24hr ephemeral story."""

    IMAGE, VIDEO = "image", "video"
    MEDIA_TYPES = [(IMAGE, "Image"), (VIDEO, "Video")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, related_name="stories", on_delete=models.CASCADE)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES, default=IMAGE)
    file_url = models.URLField()
    caption = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at


class StorySticker(models.Model):
    POLL, QUESTION, COUNTDOWN, LINK = "poll", "question", "countdown", "link"
    STICKER_TYPES = [(POLL, "Poll"), (QUESTION, "Question"), (COUNTDOWN, "Countdown"), (LINK, "Link")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, related_name="stickers", on_delete=models.CASCADE)
    sticker_type = models.CharField(max_length=10, choices=STICKER_TYPES)
    # Flexible payload: poll options, question prompt, countdown target ISO time, link URL
    data = models.JSONField(default=dict, blank=True)
    pos_x = models.FloatField(default=0.5)
    pos_y = models.FloatField(default=0.5)


class StoryView(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, related_name="views", on_delete=models.CASCADE)
    viewer = models.ForeignKey(User, related_name="story_views", on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("story", "viewer")


class Reel(models.Model):
    """Short vertical video with its own discovery feed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, related_name="reels", on_delete=models.CASCADE)
    video_url = models.URLField()
    thumbnail_url = models.URLField(blank=True)
    caption = models.TextField(blank=True)
    audio_title = models.CharField(max_length=150, blank=True, help_text="e.g. 'Original audio - sienna'")
    audio_url = models.URLField(blank=True)
    effect_tags = models.JSONField(default=list, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    share_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.reel_comments.count()


class ReelComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reel = models.ForeignKey(Reel, related_name="reel_comments", on_delete=models.CASCADE)
    author = models.ForeignKey(User, related_name="reel_comments", on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
