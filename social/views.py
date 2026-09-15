from django.contrib.auth import get_user_model
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
        """POST /api/follow/  {target_username}  -> follow / send follow request."""
        target = User.objects.get(username=request.data["target_username"])
        if target == request.user:
            return Response({"detail": "Cannot follow yourself"}, status=status.HTTP_400_BAD_REQUEST)
        follow, created = Follow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            follow.delete()
            return Response({"following": False})
        if follow.status == Follow.ACCEPTED:
            Notification.objects.create(recipient=target, actor=request.user, notification_type="follow")
        else:
            Notification.objects.create(recipient=target, actor=request.user, notification_type="follow_request")
        return Response(FollowSerializer(follow).data)

    @action(detail=False, methods=["get"])
    def requests(self, request):
        """Pending follow requests targeting the current (private) user."""
        qs = Follow.objects.filter(following=request.user, status=Follow.PENDING)
        return Response(FollowSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"], url_path="requests/(?P<follow_id>[^/.]+)/accept")
    def accept_request(self, request, follow_id=None):
        follow = Follow.objects.get(id=follow_id, following=request.user)
        follow.status = Follow.ACCEPTED
        follow.save()
        return Response(FollowSerializer(follow).data)

    @action(detail=False, methods=["post"], url_path="requests/(?P<follow_id>[^/.]+)/decline")
    def decline_request(self, request, follow_id=None):
        Follow.objects.filter(id=follow_id, following=request.user).delete()
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

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user).prefetch_related("participants", "messages")

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        convo = self.get_object()
        if request.method == "POST":
            serializer = MessageSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            message = serializer.save(sender=request.user, conversation=convo)
            message.read_by.add(request.user)
            return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
        return Response(MessageSerializer(convo.messages.select_related("sender"), many=True).data)
