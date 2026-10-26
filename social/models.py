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
        # A brand-new follow of a private account starts as a request. Only on
        # creation: accepting a request re-saves it with status=ACCEPTED.
        if self._state.adding and self.following.is_private:
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


class Block(models.Model):
    """
    `blocker` and `blocked` stop seeing each other's posts, reels, stories,
    comments and profile, can't follow or message each other, and any follow
    between them is removed (see social/visibility.py).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(User, related_name="blocking", on_delete=models.CASCADE)
    blocked = models.ForeignKey(User, related_name="blocked_by", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class Report(models.Model):
    """Something a user flagged for the Nepo team to review in the admin."""

    SPAM, NUDITY, HARASSMENT, HATE, VIOLENCE, SCAM, FALSE_INFO, OTHER = (
        "spam", "nudity", "harassment", "hate", "violence", "scam", "false_info", "other",
    )
    REASON_CHOICES = [
        (SPAM, "Spam"), (NUDITY, "Nudity or sexual content"), (HARASSMENT, "Bullying or harassment"),
        (HATE, "Hate speech"), (VIOLENCE, "Violence or dangerous acts"), (SCAM, "Scam or fraud"),
        (FALSE_INFO, "False information"), (OTHER, "Something else"),
    ]
    OPEN, RESOLVED, DISMISSED = "open", "resolved", "dismissed"
    STATUS_CHOICES = [(OPEN, "Open"), (RESOLVED, "Resolved (action taken)"), (DISMISSED, "Dismissed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Kept if the reporter deletes their account: the content may still need action.
    reporter = models.ForeignKey(User, null=True, related_name="reports_made", on_delete=models.SET_NULL)
    # Whose account or content was reported (for content: its author).
    reported_user = models.ForeignKey(User, related_name="reports_received", on_delete=models.CASCADE)
    # The report outlives removed content, as a record of what was done.
    post = models.ForeignKey("content.Post", null=True, blank=True, on_delete=models.SET_NULL)
    comment = models.ForeignKey("content.Comment", null=True, blank=True, on_delete=models.SET_NULL)
    reel = models.ForeignKey("content.Reel", null=True, blank=True, on_delete=models.SET_NULL)
    reel_comment = models.ForeignKey("content.ReelComment", null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def target(self):
        return self.post or self.comment or self.reel or self.reel_comment or self.reported_user

    def __str__(self):
        return f"{self.get_reason_display()} report on {self.target}"
