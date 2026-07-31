from django.db import models


class StoredFile(models.Model):
    """A single uploaded media asset persisted in the primary database.

    Brand logos and signature images are written here (via
    ``crm.storage.DatabaseStorage``) instead of the container filesystem, so they
    survive Cloud Run's ephemeral, per-instance disk and every redeploy/scale
    event. The existing Supabase PostgreSQL instance is the single source of
    truth for both structured data and these binary assets — no object-storage
    bucket or persistent volume is required.
    """

    # The storage "name" (e.g. ``logos/logo_fuel_mark.png``). Unique so a save
    # to the same name overwrites in place rather than orphaning a row.
    name = models.CharField(max_length=400, unique=True, db_index=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
