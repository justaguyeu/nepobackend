from django.contrib import admin

from .models import BusinessCategory, BusinessProfile

admin.site.register([BusinessCategory, BusinessProfile])
