from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from content.models import Post
from social.models import Follow

User = get_user_model()

STRONG_PASSWORD = "kilimanjaro-sunrise-42"


def register_payload(**overrides):
    return {
        "username": "newbie", "email": "n@example.com", "password": STRONG_PASSWORD,
        "full_name": "New Bie", "is_business": True, "accepted_terms": True, **overrides,
    }


class AuthTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache

    def test_register_then_login(self):
        res = self.client.post("/api/auth/register/", register_payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("access", res.data)
        user = User.objects.get(username="newbie")
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertTrue(user.terms_version)
        res = self.client.post("/api/auth/login/", {"username": "newbie", "password": STRONG_PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_register_requires_accepting_terms(self):
        for value in (False, None):
            payload = register_payload(accepted_terms=value)
            if value is None:
                payload.pop("accepted_terms")
            res = self.client.post("/api/auth/register/", payload, format="json")
            self.assertEqual(res.status_code, 400)
            self.assertIn("accepted_terms", res.data)
        self.assertFalse(User.objects.exists())

    def test_weak_passwords_rejected(self):
        for weak in ("password123", "12345678", "short", "newbie2024"):
            res = self.client.post("/api/auth/register/", register_payload(password=weak), format="json")
            self.assertEqual(res.status_code, 400, weak)
            self.assertIn("password", res.data)

    def test_duplicate_username_and_email_case_insensitive(self):
        User.objects.create_user(username="Shop", email="owner@example.com", password=STRONG_PASSWORD)
        res = self.client.post("/api/auth/register/", register_payload(username="shop"), format="json")
        self.assertIn("username", res.data)
        res = self.client.post("/api/auth/register/", register_payload(email="OWNER@example.com"), format="json")
        self.assertIn("email", res.data)

    def test_login_is_rate_limited(self):
        User.objects.create_user(username="alice", password=STRONG_PASSWORD)
        codes = [
            self.client.post("/api/auth/login/", {"username": "alice", "password": "wrong"}, format="json").status_code
            for _ in range(11)
        ]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10], 429)

    def test_refresh_rotates_and_logout_revokes(self):
        User.objects.create_user(username="alice", password=STRONG_PASSWORD)
        tokens = self.client.post("/api/auth/login/", {"username": "alice", "password": STRONG_PASSWORD}, format="json").data
        rotated = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").data
        self.assertIn("refresh", rotated)
        # The old refresh token was blacklisted by the rotation.
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": rotated["refresh"]}, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": rotated["refresh"]}, format="json").status_code, 401)

    def test_change_password_revokes_old_tokens(self):
        User.objects.create_user(username="alice", password=STRONG_PASSWORD)
        old = self.client.post("/api/auth/login/", {"username": "alice", "password": STRONG_PASSWORD}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old['access']}")
        res = self.client.post("/api/users/change_password/", {
            "old_password": STRONG_PASSWORD, "new_password": "serengeti-migration-77",
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        # The old access token no longer works; the newly issued one does.
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_change_password_validates(self):
        user = User.objects.create_user(username="alice", password=STRONG_PASSWORD)
        self.client.force_authenticate(user)
        res = self.client.post("/api/users/change_password/", {"old_password": "nope", "new_password": "serengeti-migration-77"}, format="json")
        self.assertIn("old_password", res.data)
        res = self.client.post("/api/users/change_password/", {"old_password": STRONG_PASSWORD, "new_password": "123"}, format="json")
        self.assertIn("new_password", res.data)


class ProfileTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw123456", full_name="Alice A", phone_number="+255700000000")
        self.client.force_authenticate(self.alice)

    def test_update_me(self):
        res = self.client.patch("/api/users/me/", {"bio": "hi"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["bio"], "hi")

    def test_cannot_self_verify(self):
        self.client.patch("/api/users/me/", {"is_verified": True}, format="json")
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_verified)

    def test_cannot_take_username_with_different_case(self):
        User.objects.create_user(username="bob", password="pw123456")
        res = self.client.patch("/api/users/me/", {"username": "BOB"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_phone_number_only_visible_to_owner(self):
        self.assertEqual(self.client.get("/api/users/me/").data["phone_number"], "+255700000000")
        bob = User.objects.create_user(username="bob", password="pw123456")
        self.client.force_authenticate(bob)
        self.assertNotIn("phone_number", self.client.get("/api/users/alice/").data)

    def test_search_users(self):
        User.objects.create_user(username="bob_shop", password="pw123456", full_name="Bob's Shop")
        res = self.client.get("/api/users/?search=shop")
        self.assertEqual([u["username"] for u in res.data["results"]], ["bob_shop"])


class PrivateAccountTests(APITestCase):
    def setUp(self):
        self.private = User.objects.create_user(username="priv", password="pw123456", is_private=True)
        self.viewer = User.objects.create_user(username="viewer", password="pw123456")
        self.post = Post.objects.create(author=self.private, caption="secret")
        self.client.force_authenticate(self.viewer)

    def test_private_content_hidden_until_follow_accepted(self):
        self.assertEqual(self.client.get(f"/api/posts/{self.post.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/posts/?username=priv").data["results"], [])
        self.assertEqual(self.client.get(f"/api/comments/?post={self.post.id}").data["results"], [])
        self.assertEqual(self.client.post(f"/api/posts/{self.post.id}/like/").status_code, 404)
        res = self.client.post("/api/comments/", {"post": str(self.post.id), "text": "hi"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get("/api/users/priv/followers/").status_code, 403)
        # Profile basics stay visible so people can send a follow request.
        self.assertEqual(self.client.get("/api/users/priv/").status_code, 200)

        follow = Follow.objects.create(follower=self.viewer, following=self.private)  # starts pending
        self.assertEqual(self.client.get(f"/api/posts/{self.post.id}/").status_code, 404)
        follow.status = Follow.ACCEPTED
        follow.save()
        self.assertEqual(self.client.get(f"/api/posts/{self.post.id}/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/posts/{self.post.id}/like/").status_code, 200)
        self.assertEqual(self.client.get("/api/users/priv/followers/").status_code, 200)

    def test_owner_sees_own_private_posts(self):
        self.client.force_authenticate(self.private)
        self.assertEqual(self.client.get(f"/api/posts/{self.post.id}/").status_code, 200)

    def test_anonymous_cannot_see_private_posts(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/posts/{self.post.id}/").status_code, 404)
