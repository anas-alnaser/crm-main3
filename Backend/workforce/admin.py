from django.contrib import admin

from .models import EmployeeWorkPolicy, WorkPolicyException, WorkSession


@admin.register(EmployeeWorkPolicy)
class EmployeeWorkPolicyAdmin(admin.ModelAdmin):
    list_display = ["user", "shift_tracking_required", "is_active", "daily_target_minutes", "timezone"]
    list_filter = ["shift_tracking_required", "is_active"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    autocomplete_fields = ["user"]


@admin.register(WorkSession)
class WorkSessionAdmin(admin.ModelAdmin):
    list_display = ["employee", "work_date", "started_at", "ended_at", "closing_reason", "credited_seconds", "auto_closed"]
    list_filter = ["closing_reason", "auto_closed", "work_date"]
    search_fields = ["employee__username"]
    date_hierarchy = "work_date"


@admin.register(WorkPolicyException)
class WorkPolicyExceptionAdmin(admin.ModelAdmin):
    list_display = ["policy", "date", "exception_type", "approved_by"]
    list_filter = ["exception_type", "date"]
