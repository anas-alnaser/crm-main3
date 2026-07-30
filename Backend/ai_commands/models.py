from django.conf import settings
from django.db import models


class AICommandLog(models.Model):
    class Tier(models.TextChoices):
        AUTO = "auto", "Auto"
        CONFIRM = "confirm", "Confirm"
        BLOCKED = "blocked", "Blocked"
        UNKNOWN = "unknown", "Unknown"

    class Outcome(models.TextChoices):
        EXECUTED = "executed", "Executed"
        CONFIRMATION_REQUIRED = "confirmation_required", "Confirmation required"
        CONFIRMED = "confirmed", "Confirmed"
        BLOCKED = "blocked", "Blocked"
        UNDONE = "undone", "Undone"
        ACTION_TAKEN = "action_taken", "Action taken"
        DRAFT_RETURNED = "draft_returned", "Draft returned"
        ERROR = "error", "Error"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ai_command_logs", on_delete=models.PROTECT)
    raw_text = models.TextField()
    resolved_intent = models.CharField(max_length=40, blank=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.UNKNOWN)
    outcome = models.CharField(max_length=30, choices=Outcome.choices)
    summary = models.TextField(blank=True)
    draft = models.JSONField(default=dict, blank=True)
    action_data = models.JSONField(default=dict, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.resolved_intent or 'unknown'} - {self.outcome}"
