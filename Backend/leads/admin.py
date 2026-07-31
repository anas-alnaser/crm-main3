from django.contrib import admin

from .models import Lead, LeadContactAttempt, LeadImportBatch


@admin.register(LeadImportBatch)
class LeadImportBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "original_filename", "uploaded_by", "assigned_to", "imported_count", "duplicate_count", "uploaded_at"]
    list_filter = ["status", "uploaded_at"]
    search_fields = ["original_filename", "source"]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["name", "original_phone", "status", "assigned_to", "created_at"]
    list_filter = ["status", "assigned_to", "source"]
    search_fields = ["name", "original_phone", "normalized_phone"]


@admin.register(LeadContactAttempt)
class LeadContactAttemptAdmin(admin.ModelAdmin):
    list_display = ["lead", "employee", "method", "outcome", "created_at"]
    list_filter = ["method", "outcome"]
