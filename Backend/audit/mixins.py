"""Reusable audit helpers for DRF viewsets.

Each CRM viewset keeps its own ``perform_create``/``perform_update`` (they set
ownership), so rather than shadow those, this mixin exposes small helpers the
viewset calls explicitly. Field snapshots are passed through the audit
redaction layer before storage.
"""
from __future__ import annotations

from .models import AuditCategory
from .services import record_event


def snapshot_fields(instance, only=None) -> dict:
    """A JSON-safe dict of an instance's concrete field values."""
    data = {}
    for field in instance._meta.concrete_fields:
        if only is not None and field.name not in only:
            continue
        if field.is_relation:
            data[field.attname] = getattr(instance, field.attname)
        else:
            value = getattr(instance, field.name)
            data[field.name] = value if isinstance(value, (int, float, bool)) or value is None else str(value)
    return data


class AuditLogMixin:
    audit_category = AuditCategory.CRM
    audit_entity_type = ""
    # Fields worth diffing on update (defaults to all concrete fields).
    audit_track_fields = None

    def _entity_type(self):
        if self.audit_entity_type:
            return self.audit_entity_type
        model = getattr(self, "queryset", None)
        if model is not None:
            return self.queryset.model.__name__
        return self.get_serializer_class().Meta.model.__name__

    def capture_old(self, instance):
        return snapshot_fields(instance, only=self.audit_track_fields)

    def audit_created(self, instance, summary=None):
        record_event(
            action="record.created",
            category=self.audit_category,
            user=self.request.user,
            request=self.request,
            entity_type=self._entity_type(),
            entity_id=instance.pk,
            summary=summary or f"{self._entity_type()} #{instance.pk} created.",
            new_values=snapshot_fields(instance, only=self.audit_track_fields),
        )

    def audit_updated(self, instance, old, summary=None):
        new = snapshot_fields(instance, only=self.audit_track_fields)
        changed_old = {k: v for k, v in old.items() if new.get(k) != v}
        changed_new = {k: v for k, v in new.items() if old.get(k) != v}
        if not changed_new:
            return
        record_event(
            action="record.updated",
            category=self.audit_category,
            user=self.request.user,
            request=self.request,
            entity_type=self._entity_type(),
            entity_id=instance.pk,
            summary=summary or f"{self._entity_type()} #{instance.pk} updated.",
            old_values=changed_old,
            new_values=changed_new,
        )

    def audit_action(self, instance, action, summary, **kwargs):
        record_event(
            action=action,
            category=self.audit_category,
            user=self.request.user,
            request=self.request,
            entity_type=self._entity_type(),
            entity_id=instance.pk,
            summary=summary,
            **kwargs,
        )
