from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from .models import Conversation, Follow, Message, Notification
from .visibility import can_view

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
        attrs["participant_ids"] = others
        return attrs

    def create(self, validated_data):
        others = validated_data.pop("participant_ids")
        convo = Conversation.objects.create(**validated_data)
        convo.participants.set([*others, self.context["request"].user])
        return convo
