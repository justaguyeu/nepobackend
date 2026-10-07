"""
Who may see a user's content. Public accounts: everyone. Private accounts:
only the owner and their accepted followers. Used by every endpoint that
returns posts, reels, stories, comments or follower lists.
"""
from django.db.models import Q

from .models import Follow


def visible_q(user, field="author"):
    """Q filter keeping only rows whose `field` (a User FK path) the viewer may see."""
    q = Q(**{f"{field}__is_private": False})
    if user is not None and user.is_authenticated:
        followed = Follow.objects.filter(follower=user, status=Follow.ACCEPTED).values("following_id")
        q |= Q(**{field: user}) | Q(**{f"{field}__in": followed})
    return q


def can_view(user, author):
    if not author.is_private:
        return True
    if user is None or not user.is_authenticated:
        return False
    return author.pk == user.pk or Follow.objects.filter(
        follower=user, following=author, status=Follow.ACCEPTED
    ).exists()
