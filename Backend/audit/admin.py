from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "category", "action", "entity_type", "entity_id", "source"]
    list_filter = ["category", "source", "created_at"]
    search_fields = ["action", "summary", "entity_type", "entity_id"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
