from rest_framework import serializers

from accounts.models import User

from .models import EmployeeWorkPolicy, WorkPolicyException, WorkSession
from .timezones import WEEKDAY_LABELS


def humanize_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


class EmployeeWorkPolicySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    employee_name = serializers.SerializerMethodField()
    working_day_labels = serializers.SerializerMethodField()
    last_modified_by_username = serializers.CharField(source="last_modified_by.username", read_only=True)

    class Meta:
        model = EmployeeWorkPolicy
        fields = [
            "id",
            "user",
            "username",
            "employee_name",
            "shift_tracking_required",
            "is_active",
            "timezone",
            "employment_start_date",
            "employment_end_date",
            "working_days",
            "working_day_labels",
            "earliest_start_time",
            "latest_end_time",
            "daily_target_minutes",
            "monthly_target_minutes",
            "basic_salary",
            "salary_currency",
            "overtime_allowed",
            "created_at",
            "updated_at",
            "last_modified_by",
            "last_modified_by_username",
        ]
        read_only_fields = ["created_at", "updated_at", "last_modified_by"]

    def get_employee_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_working_day_labels(self, obj):
        return obj.working_day_labels()

    def validate_working_days(self, value):
        if not isinstance(value, list) or not all(isinstance(d, int) and 0 <= d <= 6 for d in value):
            raise serializers.ValidationError("working_days must be a list of integers 0 (Mon) – 6 (Sun).")
        return sorted(set(value))

    def validate(self, attrs):
        start = attrs.get("earliest_start_time") or getattr(self.instance, "earliest_start_time", None)
        end = attrs.get("latest_end_time") or getattr(self.instance, "latest_end_time", None)
        if start and end and end <= start:
            raise serializers.ValidationError({"latest_end_time": "End time must be after the start time."})
        return attrs


class WorkPolicyExceptionSerializer(serializers.ModelSerializer):
    approved_by_username = serializers.CharField(source="approved_by.username", read_only=True)

    class Meta:
        model = WorkPolicyException
        fields = [
            "id",
            "policy",
            "date",
            "exception_type",
            "custom_start_time",
            "custom_end_time",
            "reason",
            "approved_by",
            "approved_by_username",
            "created_at",
        ]
        read_only_fields = ["approved_by", "created_at"]


class WorkSessionSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    credited_minutes = serializers.IntegerField(read_only=True)
    closing_reason_display = serializers.CharField(source="get_closing_reason_display", read_only=True)

    class Meta:
        model = WorkSession
        fields = [
            "id",
            "employee",
            "employee_name",
            "work_date",
            "started_at",
            "ended_at",
            "last_activity_at",
            "closing_reason",
            "closing_reason_display",
            "credited_seconds",
            "credited_minutes",
            "auto_closed",
            "timezone",
            "daily_target_minutes",
            "window_start_time",
            "window_end_time",
            "created_at",
        ]

    def get_employee_name(self, obj):
        return obj.employee.get_full_name() or obj.employee.username


class WeekdayReferenceSerializer(serializers.Serializer):
    """Read-only helper describing the weekday integer convention for the UI."""

    def to_representation(self, instance):
        return [{"value": value, "label": label} for value, label in sorted(WEEKDAY_LABELS.items())]


class AssignablePolicyUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "role", "is_active"]

    def get_display_name(self, obj):
        return obj.get_full_name() or obj.username
