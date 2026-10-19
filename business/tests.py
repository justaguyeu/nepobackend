from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import BusinessCategory, BusinessProfile

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


class BusinessCategoryTests(APITestCase):
    def test_lists_every_seeded_category_alphabetically_with_other_last(self):
        res = self.client.get("/api/business-categories/")
        self.assertEqual(res.status_code, 200)
        names = [c["name"] for c in res.data]  # unpaginated: the whole list in one response
        self.assertGreater(len(names), 12)
        self.assertEqual(names[-1], "Other")
        self.assertEqual(names[:-1], sorted(names[:-1]))

    def test_business_can_pick_a_category(self):
        owner = User.objects.create_user(username="cafe", password="pw123456", is_business=True)
        self.client.force_authenticate(owner)
        food = BusinessCategory.objects.get(name="Food & Restaurants")
        res = self.client.post("/api/businesses/", {"category_id": food.id}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["category"]["name"], "Food & Restaurants")
