"""
Who may see a user's content. Public accounts: everyone. Private accounts:
only the owner and their accepted followers. Blocking (either way) hides
everything in both directions. Used by every endpoint that returns posts,
reels, stories, comments, notifications or follower lists.
"""
from django.db.models import Q

from .models import Block, Follow


def not_blocked_q(user, field="author"):
    """Q filter dropping rows whose `field` (a User FK path) blocked the viewer or was blocked by them."""
    if user is None or not user.is_authenticated:
        return Q()
    return (
        ~Q(**{f"{field}__in": Block.objects.filter(blocker=user).values("blocked_id")})
        & ~Q(**{f"{field}__in": Block.objects.filter(blocked=user).values("blocker_id")})
    )


def visible_q(user, field="author"):
    """Q filter keeping only rows whose `field` (a User FK path) the viewer may see."""
    q = Q(**{f"{field}__is_private": False})
    if user is not None and user.is_authenticated:
        followed = Follow.objects.filter(follower=user, status=Follow.ACCEPTED).values("following_id")
        q |= Q(**{field: user}) | Q(**{f"{field}__in": followed})
    return q & not_blocked_q(user, field)


def is_blocked_between(user, other):
    if user is None or not user.is_authenticated or user.pk == other.pk:
        return False
    return Block.objects.filter(
        Q(blocker=user, blocked=other) | Q(blocker=other, blocked=user)
    ).exists()


def can_view(user, author):
    if is_blocked_between(user, author):
        return False
    if not author.is_private:
        return True
    if user is None or not user.is_authenticated:
        return False
    return author.pk == user.pk or Follow.objects.filter(
        follower=user, following=author, status=Follow.ACCEPTED
    ).exists()
