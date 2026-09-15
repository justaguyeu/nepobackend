from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Highlight
from .serializers import (
    ChangePasswordSerializer, HighlightSerializer, UserProfileSerializer, UserRegisterSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserProfileSerializer(user, context={"request": request}).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/users/, /api/users/{username}/, plus profile actions."""

    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    lookup_field = "username"
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=["get", "patch"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        if request.method == "PATCH":
            serializer = self.get_serializer(request.user, data=request.data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(request.user, context={"request": request}).data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"old_password": ["Wrong password."]}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password updated successfully."})

    @action(detail=True, methods=["get"])
    def followers(self, request, username=None):
        user = self.get_object()
        follower_users = User.objects.filter(following__following=user, following__status="accepted")
        return Response(UserProfileSerializer(follower_users, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def following(self, request, username=None):
        user = self.get_object()
        following_users = User.objects.filter(followers__follower=user, followers__status="accepted")
        return Response(UserProfileSerializer(following_users, many=True, context={"request": request}).data)


class HighlightViewSet(viewsets.ModelViewSet):
    serializer_class = HighlightSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Highlight.objects.filter(owner__username=self.kwargs.get("user_username"))

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
