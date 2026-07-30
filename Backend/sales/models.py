from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from clients.models import Client


class Pipeline(models.Model):
    name = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Stage(models.Model):
    pipeline = models.ForeignKey(Pipeline, related_name="stages", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta:
        ordering = ["pipeline", "order", "name"]
        unique_together = ["pipeline", "name"]

    def __str__(self):
        return f"{self.pipeline} - {self.name}"


class Deal(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    title = models.CharField(max_length=255)
    company = models.ForeignKey(Client, related_name="deals", on_delete=models.CASCADE)
    contact_person = models.CharField(max_length=255, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="JOD")
    pipeline = models.ForeignKey(Pipeline, related_name="deals", on_delete=models.PROTECT)
    stage = models.ForeignKey(Stage, related_name="deals", on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="deals", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    expected_close_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def save(self, *args, **kwargs):
        if self.stage_id:
            if self.stage.is_won:
                self.status = self.Status.WON
            elif self.stage.is_lost:
                self.status = self.Status.LOST
            else:
                self.status = self.Status.OPEN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class SalesSettings(models.Model):
    commission_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=12,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sales settings"
        verbose_name_plural = "Sales settings"

    def __str__(self):
        return f"Commission rate: {self.commission_rate_percent}%"

    @classmethod
    def load(cls):
        settings_obj, _created = cls.objects.get_or_create(pk=1)
        return settings_obj
