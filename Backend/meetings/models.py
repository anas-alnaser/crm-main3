from django.conf import settings
from django.db import models

from clients.models import Client
from sales.models import Deal


class Meeting(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    deal = models.ForeignKey(Deal, related_name="meetings", on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey(Client, related_name="meetings", on_delete=models.SET_NULL, null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="meetings", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_datetime", "title"]

    def __str__(self):
        return f"{self.title} - {self.start_datetime:%Y-%m-%d %H:%M}"
