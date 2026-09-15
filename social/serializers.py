from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from .models import Conversation, Follow, Message, Notification


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
        read_only_fields = ["sender", "read_by"]


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

    def create(self, validated_data):
        participant_ids = validated_data.pop("participant_ids", [])
        convo = Conversation.objects.create(**validated_data)
        request = self.context.get("request")
        convo.participants.set(list(set(participant_ids + ([request.user.id] if request else []))))
        return convo
