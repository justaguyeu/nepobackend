from django.db.models import Q, Count
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nepo.pagination import IdOrderedCursorPagination
from social.models import Follow, Notification
from .models import Comment, Hashtag, Like, Post, Reel, ReelComment, SavedPost, Story, StoryView
from .serializers import (
    CommentSerializer, HashtagSerializer, PostSerializer, ReelCommentSerializer,
    ReelSerializer, SavedPostSerializer, StorySerializer, StoryViewerSerializer,
)


class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        author = getattr(obj, "author", None)
        return author == request.user


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]

    def get_queryset(self):
        qs = Post.objects.select_related("author").prefetch_related("media", "hashtags")
        username = self.request.query_params.get("username")
        if username:
            qs = qs.filter(author__username=username)
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"])
    def feed(self, request):
        """Following feed: posts from accounts the user follows (+ own posts)."""
        following_ids = Follow.objects.filter(
            follower=request.user, status="accepted"
        ).values_list("following_id", flat=True)
        qs = self.get_queryset().filter(Q(author_id__in=following_ids) | Q(author=request.user))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"])
    def explore(self, request):
        """Algorithmic-ish discovery grid: rank by recent engagement, not follows."""
        qs = self.get_queryset().annotate(
            engagement=Count("likes") + Count("comments") * 2
        ).order_by("-engagement", "-created_at")
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        post = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, post=post)
        if not created:
            like.delete()
            return Response({"liked": False, "like_count": post.like_count})
        if post.author != request.user:
            Notification.objects.create(recipient=post.author, actor=request.user, notification_type="like", post=post)
        return Response({"liked": True, "like_count": post.like_count})

    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        post = self.get_object()
        collection = request.data.get("collection_name", "All Posts")
        saved, created = SavedPost.objects.get_or_create(user=request.user, post=post, collection_name=collection)
        if not created:
            saved.delete()
            return Response({"saved": False})
        return Response({"saved": True})


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Comment.objects.select_related("author").filter(parent__isnull=True)
        post_id = self.request.query_params.get("post")
        if post_id:
            qs = qs.filter(post_id=post_id)
        return qs

    def perform_create(self, serializer):
        comment = serializer.save(author=self.request.user)
        if comment.post.author != self.request.user:
            Notification.objects.create(
                recipient=comment.post.author, actor=self.request.user,
                notification_type="comment", post=comment.post, comment=comment,
            )

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        comment = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, comment=comment)
        if not created:
            like.delete()
            return Response({"liked": False, "like_count": comment.like_count})
        return Response({"liked": True, "like_count": comment.like_count})


class SavedPostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SavedPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SavedPost.objects.filter(user=self.request.user).select_related("post")


class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Story.objects.filter(expires_at__gt=timezone.now()).select_related("author")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"])
    def feed(self, request):
        """Stories grouped by author, from people you follow (+ your own), unexpired."""
        following_ids = Follow.objects.filter(
            follower=request.user, status="accepted"
        ).values_list("following_id", flat=True)
        qs = self.get_queryset().filter(Q(author_id__in=following_ids) | Q(author=request.user))
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def view(self, request, pk=None):
        story = self.get_object()
        StoryView.objects.get_or_create(story=story, viewer=request.user)
        return Response({"ok": True})

    @action(detail=True, methods=["get"])
    def viewers(self, request, pk=None):
        story = self.get_object()
        if story.author != request.user:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        return Response(StoryViewerSerializer(story.views.select_related("viewer"), many=True).data)


class ReelViewSet(viewsets.ModelViewSet):
    serializer_class = ReelSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]

    def get_queryset(self):
        qs = Reel.objects.select_related("author")
        username = self.request.query_params.get("username")
        if username:
            qs = qs.filter(author__username=username)
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"])
    def discover(self, request):
        """Algorithmic reels feed, independent of who you follow."""
        qs = self.get_queryset().annotate(
            engagement=Count("likes") + Count("reel_comments") * 2
        ).order_by("-engagement", "-created_at")
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        reel = self.get_object()
        like, created = Like.objects.get_or_create(user=request.user, reel=reel)
        if not created:
            like.delete()
            return Response({"liked": False, "like_count": reel.like_count})
        return Response({"liked": True, "like_count": reel.like_count})

    @action(detail=True, methods=["post"])
    def view(self, request, pk=None):
        reel = self.get_object()
        reel.view_count += 1
        reel.save(update_fields=["view_count"])
        return Response({"view_count": reel.view_count})


class ReelCommentViewSet(viewsets.ModelViewSet):
    serializer_class = ReelCommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = ReelComment.objects.select_related("author")
        reel_id = self.request.query_params.get("reel")
        if reel_id:
            qs = qs.filter(reel_id=reel_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class HashtagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HashtagSerializer
    queryset = Hashtag.objects.annotate(post_count=Count("posts"))
    lookup_field = "name"
    pagination_class = IdOrderedCursorPagination

    @action(detail=True, methods=["get"])
    def posts(self, request, name=None):
        tag = self.get_object()
        qs = tag.posts.select_related("author").prefetch_related("media")
        page = self.paginate_queryset(qs)
        serializer = PostSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"], pagination_class=None)
    def trending(self, request):
        """Top hashtags by post count — used for the frontend's Trending tab."""
        qs = self.get_queryset().filter(post_count__gt=0).order_by("-post_count")[:30]
        return Response(self.get_serializer(qs, many=True).data)
