from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["title", "client", "type", "status", "budget", "start_date", "deadline", "created_at", "updated_at"]
    list_filter = ["type", "status", "start_date", "deadline", "created_at"]
    search_fields = ["title", "client__name", "notes"]
