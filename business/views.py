from rest_framework import permissions, viewsets

from nepo.pagination import IdOrderedCursorPagination
from .models import BusinessCategory, BusinessProfile
from .serializers import BusinessCategorySerializer, BusinessProfileSerializer


class BusinessCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BusinessCategory.objects.all()
    serializer_class = BusinessCategorySerializer
    pagination_class = IdOrderedCursorPagination


class BusinessProfileViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = BusinessProfile.objects.select_related("user", "category")
    lookup_field = "user__username"
    lookup_url_kwarg = "username"
    pagination_class = IdOrderedCursorPagination

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
