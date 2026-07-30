import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


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


class AICommandConfirmation(models.Model):
    """Server-side, single-use approval for a Tier-2 AI command.

    The browser never gets to supply the fields that are executed. When a
    Tier-2 command is interpreted and passes server-side validation, the
    server stores the validated ``draft`` here and returns only an opaque id.
    Execution re-runs the stored draft inside a transaction and consumes the
    record so it can never be replayed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONSUMED = "consumed", "Consumed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ai_confirmations", on_delete=models.CASCADE)
    intent = models.CharField(max_length=40)
    tier = models.CharField(max_length=20)
    raw_text = models.TextField(blank=True)
    draft = models.JSONField(default=dict)
    preview = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.intent} - {self.status}"

    def is_expired(self, now=None):
        now = now or timezone.now()
        return now >= self.expires_at

    @property
    def is_open(self):
        return self.status == self.Status.PENDING and not self.is_expired()
