from django.contrib import admin

from .models import Conversation, Follow, Message, Notification

admin.site.register([Follow, Notification, Conversation, Message])
