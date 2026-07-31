from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True, default=None)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "user",
            "user_username",
            "work_session",
            "action",
            "category",
            "category_display",
            "source",
            "entity_type",
            "entity_id",
            "summary",
            "request_id",
            "metadata",
            "old_values",
            "new_values",
            "ip_address",
            "user_agent",
        ]
        read_only_fields = fields


# Controlled whitelist of supplemental UI telemetry the client may report.
# Unknown actions are rejected; these are the only accepted client events.
TELEMETRY_WHITELIST = {
    "page.opened",
    "nav.selected",
    "button.selected",
    "dialog.opened",
    "lead.opened",
    "contact.initiated",
    "export.requested",
    "pdf.opened",
    "brand.selected",
    "filter.applied",
}


class TelemetryIngestSerializer(serializers.Serializer):
    action = serializers.CharField(max_length=64)
    entity_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    entity_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)

    def validate_action(self, value):
        if value not in TELEMETRY_WHITELIST:
            raise serializers.ValidationError("Unknown telemetry action.")
        return value
