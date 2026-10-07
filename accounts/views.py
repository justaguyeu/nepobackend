from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from social.visibility import can_view
from .models import Highlight
from .serializers import (
    ChangePasswordSerializer, HighlightSerializer, UserProfileSerializer, UserRegisterSerializer,
)

User = get_user_model()


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(TokenObtainPairView):
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "token_refresh"


class LogoutView(TokenBlacklistView):
    """POST {refresh} — revokes the refresh token so it can't be used again."""
    throttle_scope = "token_refresh"


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "user": UserProfileSerializer(user, context={"request": request}).data,
            **issue_tokens(user),
        }, status=status.HTTP_201_CREATED)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/users/, /api/users/{username}/, plus profile actions."""

    serializer_class = UserProfileSerializer
    lookup_field = "username"
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    throttle_scope = None  # set per action (change_password uses the strict "auth" rate)

    def get_queryset(self):
        qs = User.objects.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip().lstrip("@")
        if search and self.action == "list":
            qs = qs.filter(Q(username__icontains=search) | Q(full_name__icontains=search))
        return qs

    @action(detail=False, methods=["get", "patch"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        if request.method == "PATCH":
            serializer = self.get_serializer(request.user, data=request.data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(request.user, context={"request": request}).data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated], throttle_scope="auth")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        # Every token issued before this is now revoked (CHECK_REVOKE_TOKEN);
        # hand this device fresh ones so it stays signed in.
        return Response({"detail": "Password updated successfully.", **issue_tokens(user)})

    def _require_visible(self, user):
        if not can_view(self.request.user, user):
            raise PermissionDenied("This account is private.")

    @action(detail=True, methods=["get"])
    def followers(self, request, username=None):
        user = self.get_object()
        self._require_visible(user)
        follower_users = User.objects.filter(following__following=user, following__status="accepted")
        return Response(UserProfileSerializer(follower_users, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def following(self, request, username=None):
        user = self.get_object()
        self._require_visible(user)
        following_users = User.objects.filter(followers__follower=user, followers__status="accepted")
        return Response(UserProfileSerializer(following_users, many=True, context={"request": request}).data)


class HighlightViewSet(viewsets.ModelViewSet):
    serializer_class = HighlightSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        owner = generics.get_object_or_404(User, username=self.kwargs.get("user_username"))
        if not can_view(self.request.user, owner):
            return Highlight.objects.none()
        return Highlight.objects.filter(owner=owner)

    def perform_create(self, serializer):
        if self.kwargs.get("user_username") != self.request.user.username:
            raise PermissionDenied("You can only add highlights to your own profile.")
        serializer.save(owner=self.request.user)
