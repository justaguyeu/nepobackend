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
