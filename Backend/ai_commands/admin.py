from django.contrib import admin

from .models import AICommandLog


@admin.register(AICommandLog)
class AICommandLogAdmin(admin.ModelAdmin):
    list_display = ["user", "resolved_intent", "tier", "outcome", "undone_at", "created_at"]
    list_filter = ["tier", "outcome", "resolved_intent", "undone_at", "created_at"]
    search_fields = ["user__username", "raw_text", "summary"]
    readonly_fields = ["user", "raw_text", "resolved_intent", "tier", "outcome", "summary", "draft", "action_data", "undone_at", "created_at"]
