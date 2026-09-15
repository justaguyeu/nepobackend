from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Highlight

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "full_name", "is_business"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact user data — used inside posts, comments, follower lists, etc."""

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "avatar_url", "is_verified", "is_business"]


class HighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Highlight
        fields = ["id", "title", "cover_url", "stories", "created_at"]


class UserProfileSerializer(serializers.ModelSerializer):
    followers_count = serializers.ReadOnlyField()
    following_count = serializers.ReadOnlyField()
    posts_count = serializers.ReadOnlyField()
    highlights = HighlightSerializer(many=True, read_only=True)
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "full_name", "bio", "avatar_url", "website",
            "phone_number", "is_private", "is_business", "is_verified",
            "followers_count", "following_count", "posts_count",
            "highlights", "is_following", "created_at",
        ]

    def get_is_following(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.followers.filter(follower=request.user, status="accepted").exists()
