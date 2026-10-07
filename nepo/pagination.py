from rest_framework.pagination import CursorPagination, PageNumberPagination


class DefaultCursorPagination(CursorPagination):
    """
    DRF's CursorPagination defaults to ordering="-created", which doesn't
    exist on any of our models (they all use `created_at`). Every ViewSet
    in the project relies on this as DEFAULT_PAGINATION_CLASS in settings.py
    instead of setting pagination per-view.
    """
    page_size = 12
    ordering = "-created_at"


class IdOrderedCursorPagination(CursorPagination):
    """For models with no created_at field (e.g. BusinessProfile)."""
    page_size = 12
    ordering = "-id"


class OldestFirstCursorPagination(CursorPagination):
    """Comment threads read top-to-bottom, oldest first, like a conversation."""
    page_size = 50
    ordering = "created_at"


class RankedPagination(PageNumberPagination):
    """
    CursorPagination always re-applies its own `ordering`, which would throw
    away an engagement ranking (explore, reels discover). Page numbers keep
    whatever order_by() the queryset already has.
    """
    page_size = 12
