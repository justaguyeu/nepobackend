from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("content.urls")),
    path("api/", include("social.urls")),
    path("api/", include("business.urls")),
    path("api/uploads/", include("uploads.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
