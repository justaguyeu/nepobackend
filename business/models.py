import uuid
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class BusinessCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="lucide icon name")

    def __str__(self):
        return self.name


class BusinessProfile(models.Model):
    """Extra data attached 1:1 to a User with is_business=True."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, related_name="business_profile", on_delete=models.CASCADE)
    category = models.ForeignKey(BusinessCategory, null=True, related_name="businesses", on_delete=models.SET_NULL)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    map_link = models.URLField(blank=True, help_text="Google Maps link or lat/long deep link")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user.username} (business)"
