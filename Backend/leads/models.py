from django.conf import settings
from django.db import models


class LeadStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    NO_ANSWER = "no_answer", "No answer"
    FOLLOW_UP = "follow_up", "Follow up"
    INTERESTED = "interested", "Interested"
    NOT_INTERESTED = "not_interested", "Not interested"
    CONVERTED = "converted", "Converted"


# Statuses a sales employee may set directly from a contact attempt.
SALES_SETTABLE_STATUSES = {
    LeadStatus.CONTACTED,
    LeadStatus.NO_ANSWER,
    LeadStatus.FOLLOW_UP,
    LeadStatus.INTERESTED,
    LeadStatus.NOT_INTERESTED,
}

# Terminal outcomes that require an admin (with a reason) to reopen.
TERMINAL_STATUSES = {LeadStatus.NOT_INTERESTED, LeadStatus.CONVERTED}


class LeadImportBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREVIEWED = "previewed", "Previewed"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    source = models.CharField(max_length=120, blank=True, help_text="Campaign or source label.")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="lead_import_batches", on_delete=models.SET_NULL, null=True
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="assigned_lead_batches", on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    total_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    assigned_count = models.PositiveIntegerField(default=0)
    validation_result = models.JSONField(default=dict, blank=True)

    # Optional retained file reference (not stored indefinitely by default).
    stored_file = models.FileField(upload_to="lead_imports/", null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Import {self.pk} ({self.original_filename or 'unnamed'})"


class Lead(models.Model):
    batch = models.ForeignKey(
        LeadImportBatch, related_name="leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=255)
    original_phone = models.CharField(max_length=64)
    normalized_phone = models.CharField(max_length=32, db_index=True, blank=True)
    country_context = models.CharField(max_length=8, blank=True)
    source = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="assigned_leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    follow_up_at = models.DateTimeField(null=True, blank=True)

    first_viewed_at = models.DateTimeField(null=True, blank=True)

    # Conversion linkage (preserved; a lead is never deleted on conversion).
    converted_client = models.ForeignKey(
        "clients.Client", related_name="source_leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    converted_deal = models.ForeignKey(
        "sales.Deal", related_name="source_leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="converted_leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    reopened_reason = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="created_leads", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["normalized_phone"]),
            models.Index(fields=["follow_up_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.original_phone})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class LeadContactAttempt(models.Model):
    class Method(models.TextChoices):
        CALL = "call", "Call"
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        OTHER = "other", "Other"

    class Outcome(models.TextChoices):
        REACHED = "reached", "Reached"
        NO_ANSWER = "no_answer", "No answer"
        BUSY = "busy", "Busy"
        WRONG_NUMBER = "wrong_number", "Wrong number"
        CALLBACK = "callback_requested", "Callback requested"
        INTERESTED = "interested", "Interested"
        NOT_INTERESTED = "not_interested", "Not interested"
        OTHER = "other", "Other"

    lead = models.ForeignKey(Lead, related_name="contact_attempts", on_delete=models.CASCADE)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="lead_contact_attempts", on_delete=models.SET_NULL, null=True
    )
    work_session = models.ForeignKey(
        "workforce.WorkSession", related_name="lead_contact_attempts", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CALL)
    outcome = models.CharField(max_length=24, choices=Outcome.choices)
    notes = models.TextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    resulting_status = models.CharField(max_length=20, choices=LeadStatus.choices, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["lead", "-created_at"])]

    def __str__(self):
        return f"{self.method}/{self.outcome} on lead {self.lead_id}"
