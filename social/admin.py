from django.contrib import admin, messages
from django.utils import timezone

from .models import Block, Conversation, Follow, Message, Notification, Report

admin.site.register([Follow, Notification, Conversation, Message])


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ["blocker", "blocked", "created_at"]
    search_fields = ["blocker__username", "blocked__username"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """The moderation queue: open reports first. Both app stores expect reports handled within 24 hours."""

    list_display = ["created_at", "status", "reason", "kind", "preview", "reported_user", "reporter"]
    list_filter = ["status", "reason"]
    search_fields = ["reported_user__username", "reporter__username", "details"]
    readonly_fields = ["reporter", "reported_user", "post", "comment", "reel", "reel_comment", "created_at", "resolved_at"]
    list_select_related = ["reporter", "reported_user", "post", "comment", "reel", "reel_comment"]
    actions = ["delete_content", "deactivate_accounts", "mark_resolved", "dismiss"]

    def get_ordering(self, request):
        return ["-status", "-created_at"]  # "open" sorts before "dismissed"/"resolved" descending

    @admin.display(description="What")
    def kind(self, obj):
        for name in ("post", "comment", "reel", "reel_comment"):
            if getattr(obj, f"{name}_id"):
                return name.replace("_", " ")
        return "account"

    @admin.display(description="Content")
    def preview(self, obj):
        target = obj.target
        text = getattr(target, "text", None) or getattr(target, "caption", None) or getattr(target, "bio", "")
        return (text or "")[:80]

    def _close(self, queryset, status):
        return queryset.update(status=status, resolved_at=timezone.now())

    @admin.action(description="Delete the reported content and mark resolved")
    def delete_content(self, request, queryset):
        deleted = 0
        for report in queryset:
            content = report.post or report.comment or report.reel or report.reel_comment
            if content is not None:
                content.delete()  # the report stays, with the content link emptied
                deleted += 1
        self._close(queryset, Report.RESOLVED)
        self.message_user(request, f"Deleted {deleted} piece(s) of content.", messages.SUCCESS)

    @admin.action(description="Deactivate the reported accounts (they can no longer sign in)")
    def deactivate_accounts(self, request, queryset):
        users = {report.reported_user for report in queryset if not report.reported_user.is_superuser}
        for user in users:
            user.is_active = False
            user.save(update_fields=["is_active"])
        self._close(queryset, Report.RESOLVED)
        self.message_user(request, f"Deactivated {len(users)} account(s).", messages.SUCCESS)

    @admin.action(description="Mark resolved (action taken)")
    def mark_resolved(self, request, queryset):
        self._close(queryset, Report.RESOLVED)

    @admin.action(description="Dismiss (nothing wrong)")
    def dismiss(self, request, queryset):
        self._close(queryset, Report.DISMISSED)
