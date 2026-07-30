from django.contrib import admin

from .models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "start_datetime", "end_datetime", "deal", "company", "status"]
    list_filter = ["status", "owner", "start_datetime", "created_at"]
    search_fields = ["title", "description", "location", "owner__username", "company__name", "deal__title"]
    autocomplete_fields = ["owner", "deal", "company"]
    ordering = ["start_datetime"]
