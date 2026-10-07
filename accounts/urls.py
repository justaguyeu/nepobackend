from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import HighlightViewSet, LoginView, LogoutView, RefreshView, RegisterView, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("users/<str:user_username>/highlights/", HighlightViewSet.as_view({"get": "list", "post": "create"})),
] + router.urls
