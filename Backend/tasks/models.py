from django.conf import settings
from django.db import models

from clients.models import Client
from projects.models import Project
from sales.models import Deal


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "Todo"
        DOING = "doing", "Doing"
        DONE = "done", "Done"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, related_name="tasks", on_delete=models.SET_NULL, null=True, blank=True)
    client = models.ForeignKey(Client, related_name="tasks", on_delete=models.SET_NULL, null=True, blank=True)
    deal = models.ForeignKey(Deal, related_name="tasks", on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return self.title
