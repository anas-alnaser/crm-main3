"""Database-backed media storage.

Uploaded media (brand logos, signature images) is stored as rows in the primary
database — the existing Supabase PostgreSQL instance — rather than on the
container's local filesystem. Cloud Run's filesystem is in-memory, per-instance,
and discarded on every restart/redeploy, so a ``FileSystemStorage`` MEDIA_ROOT
would silently lose every uploaded logo and signature. Keeping the bytes in
Postgres makes uploads durable with zero extra infrastructure or cost.

Enabled automatically in production (see ``crm.settings``); files are served back
out by ``crm.views.serve_stored_media``.
"""
from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    """Store file contents in the ``mediastore.StoredFile`` table."""

    def _model(self):
        # Imported lazily: the storage backend is instantiated while Django is
        # still wiring up, before the app registry is ready.
        from mediastore.models import StoredFile

        return StoredFile

    # --- read -------------------------------------------------------------
    def _open(self, name, mode="rb"):
        row = self._model().objects.filter(name=name).first()
        if row is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(row.content), name=name)

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def size(self, name):
        row = self._model().objects.filter(name=name).only("size").first()
        return row.size if row else 0

    # --- write ------------------------------------------------------------
    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        content_type = getattr(content, "content_type", "") or ""
        self._model().objects.update_or_create(
            name=name,
            defaults={"content": data, "size": len(data), "content_type": content_type},
        )
        return name

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def get_available_name(self, name, max_length=None):
        # Names are already made unique/safe by the upload views; overwrite in
        # place (``update_or_create``) instead of appending a random suffix,
        # which would orphan rows.
        return name

    # --- serving ----------------------------------------------------------
    def url(self, name):
        base = settings.MEDIA_URL
        if not base.endswith("/"):
            base = base + "/"
        return urljoin(base, str(name).lstrip("/"))
