from django.db.models import Case, When
from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError

from nepo.pagination import IdOrderedCursorPagination
from .models import BusinessCategory, BusinessProfile
from .serializers import BusinessCategorySerializer, BusinessProfileSerializer


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.user == request.user


class BusinessCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    # A short, fixed list that pickers show in full: alphabetical, "Other" last, unpaginated.
    queryset = BusinessCategory.objects.order_by(Case(When(name="Other", then=1), default=0), "name")
    serializer_class = BusinessCategorySerializer
    pagination_class = None


class BusinessProfileViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    queryset = BusinessProfile.objects.select_related("user", "category")
    lookup_field = "user__username"
    lookup_url_kwarg = "username"
    pagination_class = IdOrderedCursorPagination

    def perform_create(self, serializer):
        if BusinessProfile.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "You already have a business profile; update it instead."})
        serializer.save(user=self.request.user)
