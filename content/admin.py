from django.contrib import admin

from .models import (
    Comment, Hashtag, Like, Post, PostMedia, Reel, ReelComment,
    SavedPost, Story, StorySticker, StoryView,
)

admin.site.register([Post, PostMedia, Comment, Like, Hashtag, SavedPost, Story, StorySticker, StoryView, Reel, ReelComment])
