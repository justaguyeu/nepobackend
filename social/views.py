from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Conversation, Follow, Message, Notification
from .serializers import (
    ConversationSerializer, FollowSerializer, MessageSerializer, NotificationSerializer,
)

User = get_user_model()


class FollowViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request):
        """
        POST /api/follow/  {target_username}  -> toggles follow / follow request.
        Always answers {following, status} where status is "accepted",
        "pending" (request sent to a private account) or "none" (unfollowed).
        """
        username = request.data.get("target_username")
        if not username:
            return Response({"target_username": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        target = get_object_or_404(User, username=username)
        if target == request.user:
            return Response({"detail": "Cannot follow yourself"}, status=status.HTTP_400_BAD_REQUEST)
        follow, created = Follow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            follow.delete()
            Notification.objects.filter(
                recipient=target, actor=request.user, notification_type__in=["follow", "follow_request"],
            ).delete()
            return Response({"following": False, "status": "none"})
        notification_type = "follow" if follow.status == Follow.ACCEPTED else "follow_request"
        Notification.objects.create(recipient=target, actor=request.user, notification_type=notification_type)
        return Response({
            **FollowSerializer(follow).data,
            "following": follow.status == Follow.ACCEPTED,
        })

    @action(detail=False, methods=["get"])
    def requests(self, request):
        """Pending follow requests targeting the current (private) user."""
        qs = Follow.objects.filter(following=request.user, status=Follow.PENDING).select_related("follower")
        return Response(FollowSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"], url_path="requests/(?P<follow_id>[^/.]+)/accept")
    def accept_request(self, request, follow_id=None):
        follow = get_object_or_404(Follow, id=follow_id, following=request.user)
        follow.status = Follow.ACCEPTED
        follow.save()
        Notification.objects.filter(
            recipient=request.user, actor=follow.follower, notification_type="follow_request",
        ).update(notification_type="follow")
        return Response(FollowSerializer(follow).data)

    @action(detail=False, methods=["post"], url_path="requests/(?P<follow_id>[^/.]+)/decline")
    def decline_request(self, request, follow_id=None):
        follow = get_object_or_404(Follow, id=follow_id, following=request.user, status=Follow.PENDING)
        Notification.objects.filter(
            recipient=request.user, actor=follow.follower, notification_type="follow_request",
        ).delete()
        follow.delete()
        return Response({"ok": True})


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related("actor")

    @action(detail=False, methods=["post"])
    def mark_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response({"ok": True})


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    # No edit/delete: one participant mustn't be able to wipe a shared thread.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user).prefetch_related("participants", "messages")

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        convo = self.get_object()
        if request.method == "POST":
            serializer = MessageSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            message = serializer.save(sender=request.user, conversation=convo)
            message.read_by.add(request.user)
            return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
        messages = convo.messages.select_related("sender").prefetch_related("read_by")
        for unread in messages.exclude(read_by=request.user):
            unread.read_by.add(request.user)
        return Response(MessageSerializer(messages, many=True).data)
