from rest_framework.routers import DefaultRouter

from .views import (
    CommentViewSet, HashtagViewSet, PostViewSet, ReelCommentViewSet,
    ReelViewSet, SavedPostViewSet, StoryViewSet,
)

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")
router.register("comments", CommentViewSet, basename="comment")
router.register("saved", SavedPostViewSet, basename="saved-post")
router.register("stories", StoryViewSet, basename="story")
router.register("reels", ReelViewSet, basename="reel")
router.register("reel-comments", ReelCommentViewSet, basename="reel-comment")
router.register("hashtags", HashtagViewSet, basename="hashtag")

urlpatterns = router.urls
