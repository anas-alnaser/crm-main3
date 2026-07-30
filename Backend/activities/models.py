from django.conf import settings
from django.db import models

from clients.models import Client
from projects.models import Project
from sales.models import Deal


class Activity(models.Model):
    class Type(models.TextChoices):
        CALL = "call", "Call"
        MEETING = "meeting", "Meeting"
        EMAIL = "email", "Email"
        NOTE = "note", "Note"

    type = models.CharField(max_length=20, choices=Type.choices, default=Type.NOTE)
    content = models.TextField()
    client = models.ForeignKey(Client, related_name="activities", on_delete=models.SET_NULL, null=True, blank=True)
    project = models.ForeignKey(Project, related_name="activities", on_delete=models.SET_NULL, null=True, blank=True)
    deal = models.ForeignKey(Deal, related_name="activities", on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_activities",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "activities"

    def __str__(self):
        return f"{self.get_type_display()} - {self.created_at:%Y-%m-%d}"
