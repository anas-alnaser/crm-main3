from django.contrib import admin

from .models import Deal, Pipeline, SalesSettings, Stage


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "is_default"]
    list_filter = ["is_default"]
    search_fields = ["name"]


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["name", "pipeline", "order", "is_won", "is_lost"]
    list_filter = ["pipeline", "is_won", "is_lost"]
    search_fields = ["name", "pipeline__name"]
    ordering = ["pipeline", "order"]


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "value", "currency", "pipeline", "stage", "owner", "status", "expected_close_date", "updated_at"]
    list_filter = ["pipeline", "stage", "owner", "status", "currency", "expected_close_date"]
    search_fields = ["title", "company__name", "contact_person", "owner__username", "notes"]
    autocomplete_fields = ["company", "pipeline", "stage", "owner"]


@admin.register(SalesSettings)
class SalesSettingsAdmin(admin.ModelAdmin):
    list_display = ["commission_rate_percent", "updated_at"]

    def has_add_permission(self, request):
        return not SalesSettings.objects.exists()
