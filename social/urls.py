from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, FollowViewSet, NotificationViewSet

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("follow/", FollowViewSet.as_view({"post": "create"}), name="follow"),
    path("follow/requests/", FollowViewSet.as_view({"get": "requests"}), name="follow-requests"),
    path("follow/requests/<uuid:follow_id>/accept/", FollowViewSet.as_view({"post": "accept_request"})),
    path("follow/requests/<uuid:follow_id>/decline/", FollowViewSet.as_view({"post": "decline_request"})),
] + router.urls
