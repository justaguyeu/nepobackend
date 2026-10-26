from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from content.models import Comment, Post, Reel, ReelComment
from .models import Conversation, Follow, Message, Notification, Report
from .visibility import can_view, is_blocked_between

User = get_user_model()


class FollowSerializer(serializers.ModelSerializer):
    follower = UserSummarySerializer(read_only=True)
    following = UserSummarySerializer(read_only=True)

    class Meta:
        model = Follow
        fields = ["id", "follower", "following", "status", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "actor", "notification_type", "post", "reel", "comment",
            "is_read", "created_at",
        ]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSummarySerializer(read_only=True)

    class Meta:
        model = Message
        fields = [
            "id", "conversation", "sender", "kind", "text", "media_url",
            "reply_to_story", "shared_post", "read_by", "created_at",
        ]
        # The conversation comes from the URL (/conversations/{id}/messages/), not the body.
        read_only_fields = ["conversation", "sender", "read_by"]

    def validate(self, attrs):
        if not (attrs.get("text", "").strip() or attrs.get("media_url") or attrs.get("shared_post") or attrs.get("reply_to_story")):
            raise serializers.ValidationError("A message can't be empty.")
        user = self.context["request"].user
        shared = attrs.get("shared_post")
        if shared is not None and not can_view(user, shared.author):
            raise serializers.ValidationError({"shared_post": "Post not found."})
        story = attrs.get("reply_to_story")
        if story is not None and not can_view(user, story.author):
            raise serializers.ValidationError({"reply_to_story": "Story not found."})
        return attrs


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserSummarySerializer(many=True, read_only=True)
    last_message = MessageSerializer(read_only=True)
    participant_ids = serializers.ListField(write_only=True, child=serializers.UUIDField(), required=False)

    class Meta:
        model = Conversation
        fields = [
            "id", "participants", "is_group", "group_name", "group_avatar_url",
            "last_message", "created_at", "participant_ids",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        ids = set(attrs.get("participant_ids", [])) - {request.user.id}
        if not ids:
            raise serializers.ValidationError({"participant_ids": "Add at least one other person."})
        others = list(User.objects.filter(id__in=ids, is_active=True))
        if len(others) != len(ids):
            raise serializers.ValidationError({"participant_ids": "Some of those people don't exist."})
        if not attrs.get("is_group") and len(others) != 1:
            raise serializers.ValidationError({"participant_ids": "A direct conversation has exactly one other person."})
        if any(is_blocked_between(request.user, other) for other in others):
            raise serializers.ValidationError({"participant_ids": "You can't message this account."})
        attrs["participant_ids"] = others
        return attrs

    def create(self, validated_data):
        others = validated_data.pop("participant_ids")
        convo = Conversation.objects.create(**validated_data)
        convo.participants.set([*others, self.context["request"].user])
        return convo


class ReportSerializer(serializers.Serializer):
    """POST /api/reports/ {target_type, target_id, reason, details?}; target_id is a username for users."""

    TARGETS = {"post": Post, "comment": Comment, "reel": Reel, "reel_comment": ReelComment}

    target_type = serializers.ChoiceField(choices=[*TARGETS, "user"])
    target_id = serializers.CharField(max_length=150)
    reason = serializers.ChoiceField(choices=Report.REASON_CHOICES)
    details = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        user = self.context["request"].user
        kind, target_id = attrs["target_type"], attrs["target_id"]
        if kind == "user":
            target = User.objects.filter(username=target_id, is_active=True).first()
            owner = target
        else:
            try:
                target = self.TARGETS[kind].objects.select_related("author").filter(pk=target_id).first()
            except (ValueError, DjangoValidationError):  # not a UUID
                target = None
            owner = target.author if target else None
        # Only things the reporter can actually see; a 404-style message either way.
        if target is None or (owner != user and not can_view(user, owner)):
            raise serializers.ValidationError({"target_id": "We couldn't find that."})
        if owner == user:
            raise serializers.ValidationError({"target_id": "You can't report yourself."})
        attrs["target"], attrs["owner"] = target, owner
        return attrs

    def create(self, validated_data):
        kind, target = validated_data["target_type"], validated_data["target"]
        no_content = {name: None for name in self.TARGETS}
        fields = no_content if kind == "user" else {**no_content, kind: target}
        report, _ = Report.objects.get_or_create(  # reporting the same thing twice adds nothing
            reporter=self.context["request"].user, reported_user=validated_data["owner"],
            status=Report.OPEN, **fields,
            defaults={"reason": validated_data["reason"], "details": validated_data["details"]},
        )
        return report
