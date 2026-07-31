from rest_framework import serializers

from .models import Lead, LeadContactAttempt, LeadImportBatch


class LeadContactAttemptSerializer(serializers.ModelSerializer):
    employee_username = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = LeadContactAttempt
        fields = [
            "id",
            "lead",
            "employee",
            "employee_username",
            "work_session",
            "created_at",
            "method",
            "outcome",
            "notes",
            "follow_up_at",
            "resulting_status",
        ]
        read_only_fields = ["employee", "work_session", "created_at", "resulting_status"]


class LeadSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    contact_attempt_count = serializers.IntegerField(source="contact_attempts.count", read_only=True)
    is_terminal = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "batch",
            "name",
            "original_phone",
            "normalized_phone",
            "country_context",
            "source",
            "notes",
            "assigned_to",
            "assigned_to_name",
            "status",
            "status_display",
            "is_terminal",
            "follow_up_at",
            "first_viewed_at",
            "converted_client",
            "converted_deal",
            "converted_by",
            "converted_at",
            "reopened_reason",
            "contact_attempt_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "normalized_phone",
            "country_context",
            "first_viewed_at",
            "converted_client",
            "converted_deal",
            "converted_by",
            "converted_at",
            "reopened_reason",
            "batch",
        ]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to_id is None:
            return None
        return obj.assigned_to.get_full_name() or obj.assigned_to.username


class LeadImportBatchSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)

    class Meta:
        model = LeadImportBatch
        fields = [
            "id",
            "source",
            "original_filename",
            "uploaded_by",
            "uploaded_by_username",
            "assigned_to",
            "assigned_to_username",
            "uploaded_at",
            "status",
            "total_rows",
            "imported_count",
            "invalid_count",
            "duplicate_count",
            "skipped_count",
            "assigned_count",
            "validation_result",
        ]
        read_only_fields = fields
