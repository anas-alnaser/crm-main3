from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "client", "project", "deal", "status", "due_date", "created_at", "updated_at"]
    list_filter = ["status", "due_date", "created_at"]
    search_fields = ["title", "description", "client__name", "project__title", "deal__title"]
