from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserSummarySerializer
from .models import (
    Comment, Hashtag, Like, Post, PostMedia, Reel, ReelComment,
    SavedPost, Story, StorySticker, StoryView,
)


class PostMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostMedia
        fields = ["id", "media_type", "file_url", "order"]


class HashtagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hashtag
        fields = ["id", "name"]


class CommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    like_count = serializers.ReadOnlyField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "post", "author", "parent", "text", "like_count", "replies", "created_at"]
        read_only_fields = ["author"]

    def get_replies(self, obj):
        if obj.parent_id is not None:
            return []  # only nest one level deep in the default payload
        return CommentSerializer(obj.replies.all(), many=True, context=self.context).data


class PostSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    hashtags = HashtagSerializer(many=True, read_only=True)
    tagged_users = UserSummarySerializer(many=True, read_only=True)
    like_count = serializers.ReadOnlyField()
    comment_count = serializers.ReadOnlyField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    media_urls = serializers.ListField(write_only=True, child=serializers.URLField(), required=False)
    hashtag_names = serializers.ListField(write_only=True, child=serializers.CharField(), required=False)

    class Meta:
        model = Post
        fields = [
            "id", "author", "caption", "location_name", "latitude", "longitude",
            "hashtags", "tagged_users", "media", "like_count", "comment_count",
            "is_liked", "is_saved", "comments_disabled", "like_count_hidden",
            "created_at", "media_urls", "hashtag_names",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.likes.filter(user=request.user).exists()

    def get_is_saved(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.saved_by.filter(user=request.user).exists()

    def create(self, validated_data):
        media_urls = validated_data.pop("media_urls", [])
        hashtag_names = validated_data.pop("hashtag_names", [])
        post = Post.objects.create(**validated_data)
        for i, url in enumerate(media_urls):
            media_type = "video" if url.lower().endswith((".mp4", ".mov", ".webm")) else "image"
            PostMedia.objects.create(post=post, file_url=url, order=i, media_type=media_type)
        for name in hashtag_names:
            tag, _ = Hashtag.objects.get_or_create(name=name.lstrip("#").lower())
            post.hashtags.add(tag)
        return post


class StoryStickerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorySticker
        fields = ["id", "sticker_type", "data", "pos_x", "pos_y"]


class StorySerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    stickers = StoryStickerSerializer(many=True, read_only=True)
    viewer_count = serializers.SerializerMethodField()
    is_viewed = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id", "author", "media_type", "file_url", "caption",
            "stickers", "viewer_count", "is_viewed", "created_at", "expires_at",
        ]
        read_only_fields = ["expires_at"]

    def get_viewer_count(self, obj):
        return obj.views.count()

    def get_is_viewed(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.views.filter(viewer=request.user).exists()

    def create(self, validated_data):
        validated_data["expires_at"] = timezone.now() + timezone.timedelta(hours=24)
        return super().create(validated_data)


class StoryViewerSerializer(serializers.ModelSerializer):
    viewer = UserSummarySerializer(read_only=True)

    class Meta:
        model = StoryView
        fields = ["viewer", "viewed_at"]


class ReelCommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)

    class Meta:
        model = ReelComment
        fields = ["id", "reel", "author", "text", "created_at"]
        read_only_fields = ["author"]


class ReelSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    like_count = serializers.ReadOnlyField()
    comment_count = serializers.ReadOnlyField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id", "author", "video_url", "thumbnail_url", "caption",
            "audio_title", "audio_url", "effect_tags", "view_count",
            "share_count", "like_count", "comment_count", "is_liked", "created_at",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.likes.filter(user=request.user).exists()


class SavedPostSerializer(serializers.ModelSerializer):
    post = PostSerializer(read_only=True)

    class Meta:
        model = SavedPost
        fields = ["id", "post", "collection_name", "created_at"]
