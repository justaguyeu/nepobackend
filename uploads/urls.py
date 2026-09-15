from django.urls import path

from .views import upload_media

urlpatterns = [
    path("", upload_media, name="upload-media"),
]
