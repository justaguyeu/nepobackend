from rest_framework import serializers

from accounts.serializers import UserProfileSerializer
from .models import BusinessCategory, BusinessProfile


class BusinessCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessCategory
        fields = ["id", "name", "icon"]


class BusinessProfileSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    category = BusinessCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=BusinessCategory.objects.all(), source="category", write_only=True, required=False
    )

    class Meta:
        model = BusinessProfile
        fields = [
            "id", "user", "category", "category_id", "contact_phone", "contact_email",
            "whatsapp_number", "address", "map_link", "latitude", "longitude", "opening_hours",
        ]
