from django.conf import settings
from django.db import models


class AuditCategory(models.TextChoices):
    AUTH = "auth", "Authentication"
    SHIFT = "shift", "Shift"
    POLICY = "policy", "Policy"
    CRM = "crm", "CRM record"
    LEAD = "lead", "Lead"
    DOCUMENT = "document", "Document"
    USER = "user", "User administration"
    BRANDING = "branding", "Branding"
    AI = "ai", "AI command"
    SECURITY = "security", "Security"
    TELEMETRY = "telemetry", "UI telemetry"


class AuditSource(models.TextChoices):
    SERVER = "server", "Server"
    CLIENT = "client", "Client"


class AuditEvent(models.Model):
    """A single, server-authoritative record of something meaningful happening.

    The design is deliberately *not* a keylogger: it stores structured, safe
    facts (who did what to which entity, with before/after values) — never raw
    keystrokes, typed text, secrets, tokens, or authorization headers. Sensitive
    field names are stripped by ``audit.redaction`` before anything is saved.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="audit_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    work_session = models.ForeignKey(
        "workforce.WorkSession",
        related_name="audit_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=64)
    category = models.CharField(max_length=20, choices=AuditCategory.choices)
    source = models.CharField(max_length=10, choices=AuditSource.choices, default=AuditSource.SERVER)
    entity_type = models.CharField(max_length=64, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    summary = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
            models.Index(fields=["action"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["work_session"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} by {self.user_id or 'system'}"
