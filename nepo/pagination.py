from rest_framework.pagination import CursorPagination


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
