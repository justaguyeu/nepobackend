from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from social.models import Follow, Notification
from .models import Comment, Like, Post, PostMedia, Reel, ReelComment

User = get_user_model()


class ContentAPITestCase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw123456")
        self.bob = User.objects.create_user(username="bob", password="pw123456")
        self.carol = User.objects.create_user(username="carol", password="pw123456")
        self.post = Post.objects.create(author=self.alice, caption="hello")
        self.reel = Reel.objects.create(author=self.alice, video_url="https://example.com/v.mp4")

    def login(self, user):
        self.client.force_authenticate(user)


class PostLikeTests(ContentAPITestCase):
    def test_like_then_unlike_toggles_and_returns_count(self):
        self.login(self.bob)
        res = self.client.post(f"/api/posts/{self.post.id}/like/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, {"liked": True, "like_count": 1})
        res = self.client.post(f"/api/posts/{self.post.id}/like/")
        self.assertEqual(res.data, {"liked": False, "like_count": 0})

    def test_like_creates_notification_and_unlike_removes_it(self):
        self.login(self.bob)
        self.client.post(f"/api/posts/{self.post.id}/like/")
        self.assertEqual(Notification.objects.filter(recipient=self.alice, notification_type="like").count(), 1)
        self.client.post(f"/api/posts/{self.post.id}/like/")
        self.client.post(f"/api/posts/{self.post.id}/like/")
        # Re-liking must not pile up duplicate notifications.
        self.assertEqual(Notification.objects.filter(recipient=self.alice, notification_type="like").count(), 1)

    def test_post_payload_reports_is_liked(self):
        Like.objects.create(user=self.bob, post=self.post)
        self.login(self.bob)
        res = self.client.get(f"/api/posts/{self.post.id}/")
        self.assertTrue(res.data["is_liked"])
        self.assertEqual(res.data["like_count"], 1)

    def test_anonymous_cannot_like(self):
        res = self.client.post(f"/api/posts/{self.post.id}/like/")
        self.assertEqual(res.status_code, 401)

    def test_save_toggles(self):
        self.login(self.bob)
        self.assertEqual(self.client.post(f"/api/posts/{self.post.id}/save/").data, {"saved": True})
        self.assertTrue(self.client.get(f"/api/posts/{self.post.id}/").data["is_saved"])
        self.assertEqual(self.client.post(f"/api/posts/{self.post.id}/save/").data, {"saved": False})

    def test_only_author_can_delete_post(self):
        self.login(self.bob)
        self.assertEqual(self.client.delete(f"/api/posts/{self.post.id}/").status_code, 403)
        self.login(self.alice)
        self.assertEqual(self.client.delete(f"/api/posts/{self.post.id}/").status_code, 204)


class PostCreateTests(ContentAPITestCase):
    def test_video_detected_even_with_query_string(self):
        self.login(self.bob)
        res = self.client.post("/api/posts/", {
            "caption": "clip",
            "media_urls": ["https://x.supabase.co/storage/v1/object/public/m/a.mp4?", "https://x.co/b.jpg"],
            "hashtag_names": ["#Biz", "biz"],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual([m["media_type"] for m in res.data["media"]], ["video", "image"])
        self.assertEqual([h["name"] for h in res.data["hashtags"]], ["biz"])


class CommentTests(ContentAPITestCase):
    def test_create_comment_notifies_post_author(self):
        self.login(self.bob)
        res = self.client.post("/api/comments/", {"post": str(self.post.id), "text": "nice"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["author"]["username"], "bob")
        self.assertFalse(res.data["is_liked"])
        self.assertTrue(Notification.objects.filter(recipient=self.alice, notification_type="comment").exists())

    def test_comments_listed_oldest_first_with_all_pages(self):
        for i in range(15):
            Comment.objects.create(post=self.post, author=self.bob, text=f"c{i}")
        res = self.client.get(f"/api/comments/?post={self.post.id}")
        texts = [c["text"] for c in res.data["results"]]
        self.assertEqual(texts[:3], ["c0", "c1", "c2"])
        self.assertEqual(len(texts), 15)

    def test_replies_nest_under_parent_and_are_hidden_from_top_level(self):
        parent = Comment.objects.create(post=self.post, author=self.bob, text="parent")
        self.login(self.carol)
        res = self.client.post("/api/comments/", {
            "post": str(self.post.id), "text": "reply", "parent": str(parent.id),
        }, format="json")
        self.assertEqual(res.status_code, 201)
        listing = self.client.get(f"/api/comments/?post={self.post.id}").data["results"]
        self.assertEqual(len(listing), 1)
        self.assertEqual([r["text"] for r in listing[0]["replies"]], ["reply"])

    def test_reply_to_a_reply_attaches_to_top_level_thread(self):
        parent = Comment.objects.create(post=self.post, author=self.bob, text="parent")
        reply = Comment.objects.create(post=self.post, author=self.carol, parent=parent, text="reply")
        self.login(self.alice)
        res = self.client.post("/api/comments/", {
            "post": str(self.post.id), "text": "reply to reply", "parent": str(reply.id),
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["parent"], parent.id)

    def test_parent_must_belong_to_same_post(self):
        other = Post.objects.create(author=self.bob)
        foreign = Comment.objects.create(post=other, author=self.bob, text="x")
        self.login(self.carol)
        res = self.client.post("/api/comments/", {
            "post": str(self.post.id), "text": "bad", "parent": str(foreign.id),
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_cannot_comment_when_disabled(self):
        self.post.comments_disabled = True
        self.post.save()
        self.login(self.bob)
        res = self.client.post("/api/comments/", {"post": str(self.post.id), "text": "hi"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_like_top_level_comment_and_reply(self):
        parent = Comment.objects.create(post=self.post, author=self.bob, text="parent")
        reply = Comment.objects.create(post=self.post, author=self.carol, parent=parent, text="reply")
        self.login(self.alice)
        self.assertEqual(self.client.post(f"/api/comments/{parent.id}/like/").data, {"liked": True, "like_count": 1})
        self.assertEqual(self.client.post(f"/api/comments/{reply.id}/like/").data, {"liked": True, "like_count": 1})
        listing = self.client.get(f"/api/comments/?post={self.post.id}").data["results"]
        self.assertTrue(listing[0]["is_liked"])
        self.assertTrue(listing[0]["replies"][0]["is_liked"])
        self.assertEqual(self.client.post(f"/api/comments/{reply.id}/like/").data, {"liked": False, "like_count": 0})

    def test_only_comment_author_or_post_author_can_delete(self):
        comment = Comment.objects.create(post=self.post, author=self.bob, text="mine")
        self.login(self.carol)
        self.assertEqual(self.client.delete(f"/api/comments/{comment.id}/").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/comments/{comment.id}/", {"text": "hacked"}, format="json").status_code, 403)
        self.login(self.alice)  # post owner can moderate
        self.assertEqual(self.client.delete(f"/api/comments/{comment.id}/").status_code, 204)

    def test_comment_author_can_delete_own_reply(self):
        parent = Comment.objects.create(post=self.post, author=self.bob, text="parent")
        reply = Comment.objects.create(post=self.post, author=self.carol, parent=parent, text="reply")
        self.login(self.carol)
        self.assertEqual(self.client.delete(f"/api/comments/{reply.id}/").status_code, 204)


class ReelTests(ContentAPITestCase):
    def test_reel_like_toggle_and_notification(self):
        self.login(self.bob)
        self.assertEqual(self.client.post(f"/api/reels/{self.reel.id}/like/").data, {"liked": True, "like_count": 1})
        self.assertTrue(Notification.objects.filter(recipient=self.alice, reel=self.reel, notification_type="like").exists())
        self.assertEqual(self.client.post(f"/api/reels/{self.reel.id}/like/").data, {"liked": False, "like_count": 0})
        self.assertFalse(Notification.objects.filter(recipient=self.alice, reel=self.reel).exists())

    def test_reel_reports_whether_viewer_follows_author(self):
        self.login(self.bob)
        self.assertFalse(self.client.get(f"/api/reels/{self.reel.id}/").data["is_following_author"])
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.assertTrue(self.client.get(f"/api/reels/{self.reel.id}/").data["is_following_author"])

    def test_reel_comments_oldest_first_and_notify(self):
        ReelComment.objects.create(reel=self.reel, author=self.carol, text="first")
        self.login(self.bob)
        res = self.client.post("/api/reel-comments/", {"reel": str(self.reel.id), "text": "second"}, format="json")
        self.assertEqual(res.status_code, 201)
        listing = self.client.get(f"/api/reel-comments/?reel={self.reel.id}").data["results"]
        self.assertEqual([c["text"] for c in listing], ["first", "second"])
        self.assertTrue(Notification.objects.filter(recipient=self.alice, reel=self.reel, notification_type="comment").exists())

    def test_only_reel_comment_author_or_reel_owner_can_delete(self):
        comment = ReelComment.objects.create(reel=self.reel, author=self.bob, text="hi")
        self.login(self.carol)
        self.assertEqual(self.client.delete(f"/api/reel-comments/{comment.id}/").status_code, 403)
        self.login(self.bob)
        self.assertEqual(self.client.delete(f"/api/reel-comments/{comment.id}/").status_code, 204)


class RankingTests(ContentAPITestCase):
    def test_explore_ranks_by_engagement(self):
        popular = Post.objects.create(author=self.bob, caption="popular")
        PostMedia.objects.create(post=popular, file_url="https://x.co/a.jpg")
        Like.objects.create(user=self.alice, post=popular)
        Like.objects.create(user=self.carol, post=popular)
        Post.objects.create(author=self.carol, caption="newest, no likes")
        self.login(self.alice)
        res = self.client.get("/api/posts/explore/")
        self.assertEqual(res.data["results"][0]["id"], str(popular.id))

    def test_feed_shows_followed_and_own_posts_only(self):
        Post.objects.create(author=self.bob, caption="bob's")
        Post.objects.create(author=self.carol, caption="carol's")
        Follow.objects.create(follower=self.alice, following=self.bob)
        self.login(self.alice)
        captions = {p["caption"] for p in self.client.get("/api/posts/feed/").data["results"]}
        self.assertEqual(captions, {"hello", "bob's"})
