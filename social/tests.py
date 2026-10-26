from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Conversation, Follow, Notification

User = get_user_model()


class FollowTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw123456")
        self.bob = User.objects.create_user(username="bob", password="pw123456")
        self.private = User.objects.create_user(username="priv", password="pw123456", is_private=True)
        self.client.force_authenticate(self.alice)

    def test_follow_and_unfollow(self):
        res = self.client.post("/api/follow/", {"target_username": "bob"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "accepted")
        self.assertTrue(res.data["following"])
        res = self.client.post("/api/follow/", {"target_username": "bob"}, format="json")
        self.assertEqual(res.data, {"following": False, "status": "none"})
        self.assertFalse(Notification.objects.filter(recipient=self.bob, notification_type="follow").exists())

    def test_private_account_gets_request(self):
        res = self.client.post("/api/follow/", {"target_username": "priv"}, format="json")
        self.assertEqual(res.data["status"], "pending")
        self.assertFalse(res.data["following"])
        profile = self.client.get("/api/users/priv/").data
        self.assertEqual(profile["follow_status"], "pending")
        self.assertFalse(profile["is_following"])

    def test_accept_request(self):
        self.client.post("/api/follow/", {"target_username": "priv"}, format="json")
        self.client.force_authenticate(self.private)
        requests = self.client.get("/api/follow/requests/").data
        self.assertEqual(len(requests), 1)
        res = self.client.post(f"/api/follow/requests/{requests[0]['id']}/accept/")
        self.assertEqual(res.data["status"], "accepted")
        self.assertEqual(Follow.objects.get(follower=self.alice).status, "accepted")

    def test_unknown_user_is_404_not_500(self):
        self.assertEqual(self.client.post("/api/follow/", {"target_username": "ghost"}, format="json").status_code, 404)
        self.assertEqual(self.client.post("/api/follow/", {}, format="json").status_code, 400)

    def test_cannot_follow_self(self):
        self.assertEqual(self.client.post("/api/follow/", {"target_username": "alice"}, format="json").status_code, 400)


class NotificationTests(APITestCase):
    def test_mark_read(self):
        alice = User.objects.create_user(username="alice", password="pw123456")
        bob = User.objects.create_user(username="bob", password="pw123456")
        Notification.objects.create(recipient=alice, actor=bob, notification_type="follow")
        self.client.force_authenticate(alice)
        self.assertFalse(self.client.get("/api/notifications/").data["results"][0]["is_read"])
        self.client.post("/api/notifications/mark_read/")
        self.assertTrue(self.client.get("/api/notifications/").data["results"][0]["is_read"])


class ConversationTests(APITestCase):
    def test_send_and_list_messages(self):
        alice = User.objects.create_user(username="alice", password="pw123456")
        bob = User.objects.create_user(username="bob", password="pw123456")
        self.client.force_authenticate(alice)
        res = self.client.post("/api/conversations/", {"participant_ids": [str(bob.id)]}, format="json")
        self.assertEqual(res.status_code, 201)
        convo_id = res.data["id"]
        self.client.post(f"/api/conversations/{convo_id}/messages/", {"kind": "text", "text": "hi"}, format="json")
        self.client.force_authenticate(bob)
        msgs = self.client.get(f"/api/conversations/{convo_id}/messages/").data
        self.assertEqual([m["text"] for m in msgs], ["hi"])

    def test_outsider_cannot_read(self):
        alice = User.objects.create_user(username="alice", password="pw123456")
        eve = User.objects.create_user(username="eve", password="pw123456")
        convo = Conversation.objects.create()
        convo.participants.set([alice])
        self.client.force_authenticate(eve)
        self.assertEqual(self.client.get(f"/api/conversations/{convo.id}/messages/").status_code, 404)


class ConversationValidationTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw123456")
        self.client.force_authenticate(self.alice)

    def test_rejects_unknown_or_missing_participants(self):
        import uuid
        res = self.client.post("/api/conversations/", {"participant_ids": [str(uuid.uuid4())]}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/conversations/", {"participant_ids": [str(self.alice.id)]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_or_edit_conversation(self):
        bob = User.objects.create_user(username="bob", password="pw123456")
        convo = Conversation.objects.create()
        convo.participants.set([self.alice, bob])
        self.assertEqual(self.client.delete(f"/api/conversations/{convo.id}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/conversations/{convo.id}/", {"group_name": "x"}, format="json").status_code, 405)

    def test_empty_message_rejected(self):
        bob = User.objects.create_user(username="bob", password="pw123456")
        convo = Conversation.objects.create()
        convo.participants.set([self.alice, bob])
        res = self.client.post(f"/api/conversations/{convo.id}/messages/", {"kind": "text", "text": "   "}, format="json")
        self.assertEqual(res.status_code, 400)


class BlockTests(APITestCase):
    def setUp(self):
        from content.models import Comment, Post
        self.alice = User.objects.create_user(username="alice", password="pw123456")
        self.bob = User.objects.create_user(username="bob", password="pw123456")
        self.carol = User.objects.create_user(username="carol", password="pw123456")
        Follow.objects.create(follower=self.alice, following=self.bob)
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.bobs_post = Post.objects.create(author=self.bob, caption="bob's post")
        self.carols_post = Post.objects.create(author=self.carol, caption="carol's post")
        Comment.objects.create(post=self.carols_post, author=self.bob, text="bob was here")
        self.client.force_authenticate(self.alice)

    def block_bob(self):
        res = self.client.post("/api/users/bob/block/")
        self.assertEqual(res.data, {"blocked": True})

    def test_block_ends_follows_and_hides_content_both_ways(self):
        self.block_bob()
        self.assertFalse(Follow.objects.filter(follower__in=[self.alice, self.bob], following__in=[self.alice, self.bob]).exists())
        self.assertEqual(self.client.get("/api/posts/?username=bob").data["results"], [])
        comments = self.client.get(f"/api/comments/?post={self.carols_post.id}").data["results"]
        self.assertEqual(comments, [])
        self.assertTrue(self.client.get("/api/users/bob/").data["is_blocked"])
        # Bob no longer finds Alice at all.
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/users/alice/").status_code, 404)
        self.assertEqual(self.client.post("/api/follow/", {"target_username": "alice"}, format="json").status_code, 403)

    def test_blocked_people_cant_follow_or_message(self):
        convo = Conversation.objects.create()
        convo.participants.set([self.alice, self.bob])
        self.block_bob()
        self.assertEqual(self.client.post("/api/follow/", {"target_username": "bob"}, format="json").status_code, 403)
        res = self.client.post(f"/api/conversations/{convo.id}/messages/", {"text": "hi"}, format="json")
        self.assertEqual(res.status_code, 403)
        res = self.client.post("/api/conversations/", {"participant_ids": [str(self.bob.id)]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_unblock_and_blocked_list(self):
        self.block_bob()
        self.assertEqual([u["username"] for u in self.client.get("/api/users/me/blocked/").data], ["bob"])
        self.assertEqual(self.client.delete("/api/users/bob/block/").data, {"blocked": False})
        self.assertEqual(self.client.get("/api/users/me/blocked/").data, [])
        self.assertEqual(len(self.client.get("/api/posts/?username=bob").data["results"]), 1)

    def test_cannot_block_self(self):
        self.assertEqual(self.client.post("/api/users/alice/block/").status_code, 400)


class ReportTests(APITestCase):
    def setUp(self):
        from content.models import Post
        self.alice = User.objects.create_user(username="alice", password="pw123456")
        self.bob = User.objects.create_user(username="bob", password="pw123456")
        self.secret = User.objects.create_user(username="secret", password="pw123456", is_private=True)
        self.post = Post.objects.create(author=self.bob, caption="buy followers here")
        self.hidden = Post.objects.create(author=self.secret, caption="private")
        self.client.force_authenticate(self.alice)

    def report(self, **body):
        return self.client.post("/api/reports/", {"reason": "spam", **body}, format="json")

    def test_report_post_and_account(self):
        from .models import Report
        self.assertEqual(self.report(target_type="post", target_id=str(self.post.id)).status_code, 201)
        self.assertEqual(self.report(target_type="user", target_id="bob", details="fake shop").status_code, 201)
        reports = Report.objects.order_by("created_at")
        self.assertEqual([(r.reported_user, r.post) for r in reports], [(self.bob, self.post), (self.bob, None)])
        # Reporting the same thing again doesn't pile up duplicates.
        self.report(target_type="post", target_id=str(self.post.id))
        self.assertEqual(Report.objects.count(), 2)

    def test_cannot_report_what_you_cant_see_or_yourself(self):
        self.assertEqual(self.report(target_type="post", target_id=str(self.hidden.id)).status_code, 400)
        self.assertEqual(self.report(target_type="post", target_id="not-a-uuid").status_code, 400)
        self.assertEqual(self.report(target_type="user", target_id="alice").status_code, 400)
        self.assertEqual(self.report(target_type="user", target_id="bob", reason="bad").status_code, 400)

    def test_requires_sign_in(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.report(target_type="user", target_id="bob").status_code, 401)
