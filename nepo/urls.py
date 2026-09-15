from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("content.urls")),
    path("api/", include("social.urls")),
    path("api/", include("business.urls")),
    path("api/uploads/", include("uploads.urls")),
]
