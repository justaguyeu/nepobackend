import uuid
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Follow(models.Model):
    PENDING, ACCEPTED = "pending", "accepted"
    STATUS_CHOICES = [(PENDING, "Pending"), (ACCEPTED, "Accepted")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(User, related_name="following", on_delete=models.CASCADE)
    following = models.ForeignKey(User, related_name="followers", on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACCEPTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("follower", "following")

    def save(self, *args, **kwargs):
        # Auto-pend if the target account is private and not already accepted
        if self.following.is_private and self.status != self.ACCEPTED:
            self.status = self.PENDING
        super().save(*args, **kwargs)


class Notification(models.Model):
    LIKE, COMMENT, FOLLOW, FOLLOW_REQUEST, MENTION, TAG = (
        "like", "comment", "follow", "follow_request", "mention", "tag",
    )
    TYPE_CHOICES = [
        (LIKE, "Like"), (COMMENT, "Comment"), (FOLLOW, "Follow"),
        (FOLLOW_REQUEST, "Follow request"), (MENTION, "Mention"), (TAG, "Tag"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(User, related_name="notifications", on_delete=models.CASCADE)
    actor = models.ForeignKey(User, related_name="actions", on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    post = models.ForeignKey("content.Post", null=True, blank=True, on_delete=models.CASCADE)
    reel = models.ForeignKey("content.Reel", null=True, blank=True, on_delete=models.CASCADE)
    comment = models.ForeignKey("content.Comment", null=True, blank=True, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(User, related_name="conversations")
    is_group = models.BooleanField(default=False)
    group_name = models.CharField(max_length=100, blank=True)
    group_avatar_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def last_message(self):
        return self.messages.order_by("-created_at").first()


class Message(models.Model):
    TEXT, MEDIA, STORY_REPLY, POST_SHARE = "text", "media", "story_reply", "post_share"
    KIND_CHOICES = [
        (TEXT, "Text"), (MEDIA, "Media"), (STORY_REPLY, "Story reply"), (POST_SHARE, "Post share"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name="sent_messages", on_delete=models.CASCADE)
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default=TEXT)
    text = models.TextField(blank=True)
    media_url = models.URLField(blank=True)
    reply_to_story = models.ForeignKey("content.Story", null=True, blank=True, on_delete=models.SET_NULL)
    shared_post = models.ForeignKey("content.Post", null=True, blank=True, on_delete=models.SET_NULL)
    read_by = models.ManyToManyField(User, related_name="read_messages", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
