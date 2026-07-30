from django.conf import settings
from django.db import models

from clients.models import Client


class Project(models.Model):
    class Type(models.TextChoices):
        BRANDING = "branding", "Branding"
        WEB = "web", "Web"
        DEV = "dev", "Dev"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        LEAD = "lead", "Lead"
        PROPOSAL = "proposal", "Proposal"
        IN_PROGRESS = "in_progress", "In progress"
        DELIVERED = "delivered", "Delivered"
        PAID = "paid", "Paid"

    title = models.CharField(max_length=255)
    client = models.ForeignKey(Client, related_name="projects", on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.BRANDING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.LEAD)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_projects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
