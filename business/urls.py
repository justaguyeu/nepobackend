from rest_framework.routers import DefaultRouter

from .views import BusinessCategoryViewSet, BusinessProfileViewSet

router = DefaultRouter()
router.register("business-categories", BusinessCategoryViewSet, basename="business-category")
router.register("businesses", BusinessProfileViewSet, basename="business-profile")

urlpatterns = router.urls
