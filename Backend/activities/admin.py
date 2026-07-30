from django.contrib import admin

from .models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["type", "client", "project", "deal", "created_at"]
    list_filter = ["type", "created_at", "client", "project", "deal"]
    search_fields = ["content", "client__name", "project__title", "deal__title"]
