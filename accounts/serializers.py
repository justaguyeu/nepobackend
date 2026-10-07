from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import Highlight

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(required=True)
    accepted_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "full_name", "is_business", "accepted_terms"]

    def validate_username(self, value):
        # Django's uniqueness check is case-sensitive; "Shop" vs "shop" would enable impersonation.
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_accepted_terms(self, value):
        if value is not True:
            raise serializers.ValidationError("You must read and accept the Terms & Conditions to register.")
        return value

    def validate(self, attrs):
        # Run the project's AUTH_PASSWORD_VALIDATORS (length, common passwords,
        # similarity to username/email, all-numeric).
        candidate = User(username=attrs.get("username"), email=attrs.get("email"), full_name=attrs.get("full_name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        validated_data.pop("accepted_terms")
        password = validated_data.pop("password")
        user = User(
            **validated_data,
            terms_accepted_at=timezone.now(),
            terms_version=settings.TERMS_VERSION,
        )
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": ["Wrong password."]})
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact user data — used inside posts, comments, follower lists, etc."""

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "avatar_url", "is_verified", "is_business"]


class HighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Highlight
        fields = ["id", "title", "cover_url", "stories", "created_at"]

    def validate_stories(self, stories):
        request = self.context.get("request")
        if request and any(story.author_id != request.user.id for story in stories):
            raise serializers.ValidationError("Highlights can only contain your own stories.")
        return stories


class UserProfileSerializer(serializers.ModelSerializer):
    followers_count = serializers.ReadOnlyField()
    following_count = serializers.ReadOnlyField()
    posts_count = serializers.ReadOnlyField()
    highlights = HighlightSerializer(many=True, read_only=True)
    is_following = serializers.SerializerMethodField()
    follow_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "full_name", "bio", "avatar_url", "website",
            "phone_number", "is_private", "is_business", "is_verified",
            "followers_count", "following_count", "posts_count",
            "highlights", "is_following", "follow_status", "created_at",
        ]
        # Verification is granted by staff (admin), never self-assigned via PATCH /users/me/.
        read_only_fields = ["is_verified", "created_at"]

    def validate_username(self, value):
        taken = User.objects.filter(username__iexact=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        # A personal phone number is private; only its owner sees it.
        if not request or request.user != obj:
            data.pop("phone_number", None)
        return data

    def _follow(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return obj.followers.filter(follower=request.user).only("status").first()

    def get_is_following(self, obj):
        follow = self._follow(obj)
        return bool(follow and follow.status == "accepted")

    def get_follow_status(self, obj):
        """"accepted", "pending" (request sent to a private account) or "none"."""
        follow = self._follow(obj)
        return follow.status if follow else "none"
