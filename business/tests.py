from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import BusinessProfile

User = get_user_model()


class BusinessProfileTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="shop", password="pw123456", is_business=True)
        self.other = User.objects.create_user(username="other", password="pw123456")

    def test_owner_can_create_and_update(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post("/api/businesses/", {"address": "Dar"}, format="json").status_code, 201)
        res = self.client.patch("/api/businesses/shop/", {"address": "Arusha"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["address"], "Arusha")

    def test_duplicate_create_is_400(self):
        BusinessProfile.objects.create(user=self.owner)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post("/api/businesses/", {}, format="json").status_code, 400)

    def test_stranger_cannot_edit(self):
        BusinessProfile.objects.create(user=self.owner, address="Dar")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch("/api/businesses/shop/", {"address": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete("/api/businesses/shop/").status_code, 403)
