from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsAdminRole, IsOwnerOrAdmin, IsSuperAdmin
from audit.models import AuditCategory
from audit.mixins import AuditLogMixin
from audit.services import record_event
from crm import danger
from crm.throttling import DangerZoneThrottle
from workforce.permissions import ShiftRequiredForWrite
from .models import Client
from .serializers import ClientSerializer


class ClientViewSet(AuditLogMixin, ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin, ShiftRequiredForWrite]
    filterset_fields = ["status", "country", "is_archived"]
    search_fields = ["name", "contact_person", "email", "phone", "country", "notes"]
    ordering_fields = ["name", "country", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Client.objects.all()
        # Detail actions (retrieve/update/archive/restore) must be able to reach
        # archived companies; only the list view hides them by default.
        if self.action != "list":
            return queryset
        if self.request.query_params.get("archived") == "true":
            return queryset.filter(is_archived=True)
        if self.request.query_params.get("include_archived") == "true":
            return queryset
        return queryset.filter(is_archived=False)

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self.audit_created(instance, summary=f"Company '{instance.name}' created.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        instance = serializer.save()
        self.audit_updated(instance, old, summary=f"Company '{instance.name}' updated.")

    def destroy(self, request, *args, **kwargs):
        # Deleting a company would cascade to its deals and projects. Archive
        # instead so business history is preserved.
        return Response(
            {"detail": "Companies cannot be deleted. Archive the company instead.", "code": "delete_disabled"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["patch"], url_path="archive", permission_classes=[IsAdminRole])
    def archive(self, request, pk=None):
        client = self.get_object()
        if not client.is_archived:
            client.is_archived = True
            client.archived_at = timezone.now()
            client.archived_by = request.user
            client.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
            self.audit_action(client, "record.archived", f"Company '{client.name}' archived.")
        return Response(self.get_serializer(client).data)

    @action(detail=True, methods=["patch"], url_path="restore", permission_classes=[IsAdminRole])
    def restore(self, request, pk=None):
        client = self.get_object()
        if client.is_archived:
            client.is_archived = False
            client.archived_at = None
            client.archived_by = None
            client.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
            self.audit_action(client, "record.restored", f"Company '{client.name}' restored.")
        return Response(self.get_serializer(client).data)

    # -- Superadmin-only permanent deletion --------------------------------
    # Archive/Restore above remain the normal behaviour for everyone. Only a
    # superadmin may permanently delete a company, and only through this
    # explicit, re-authenticated, cascade-aware action.

    @staticmethod
    def _impact(client) -> dict:
        """Counts of dependent records. Deals and projects are *deleted* with the
        company (FK CASCADE); tasks, activities, meetings, documents, and
        conversion-linked leads are *detached* (FK SET_NULL)."""
        return {
            "deals": client.deals.count(),
            "projects": client.projects.count(),
            "tasks": client.tasks.count(),
            "activities": client.activities.count(),
            "meetings": client.meetings.count(),
            "documents": client.documents.count(),
            "converted_leads": client.source_leads.count(),
        }

    @action(
        detail=True,
        methods=["get"],
        url_path="delete-impact",
        permission_classes=[IsSuperAdmin],
        throttle_classes=[DangerZoneThrottle],
    )
    def delete_impact(self, request, pk=None):
        client = self.get_object()
        impact = self._impact(client)
        cascade_deletes = impact["deals"] + impact["projects"]
        return Response(
            {
                "client_id": client.id,
                "name": client.name,
                "is_archived": client.is_archived,
                "impact": impact,
                # Deals + projects are destroyed; everything else is unlinked.
                "cascade_delete_count": cascade_deletes,
                "dependencies_exist": any(impact.values()),
                "confirmation_phrase": "DELETE COMPANY",
            }
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="permanent-delete",
        permission_classes=[IsSuperAdmin],
        throttle_classes=[DangerZoneThrottle],
    )
    def permanent_delete(self, request, pk=None):
        client = self.get_object()

        guard = (
            danger.check_password(request)
            or danger.check_confirmation(request, "DELETE COMPANY")
            or danger.check_id_matches(request, "client_id", client.id)
        )
        if guard is not None:
            return guard

        impact = self._impact(client)
        if any(impact.values()) and not bool(request.data.get("cascade_confirmed")):
            return danger.error(
                "This company has related records. Confirm the cascade to proceed.",
                "cascade_confirmation_required",
                status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            locked = Client.objects.select_for_update().filter(pk=client.id).first()
            if locked is None:
                return danger.error("Company not found (already deleted).", "not_found", status.HTTP_404_NOT_FOUND)
            deleted_id = locked.id
            deleted_name = locked.name
            final_impact = self._impact(locked)
            # One transaction; Django deletes in FK-safe order (deals/projects
            # cascade, everything else is SET_NULL). Unrelated companies and
            # records are untouched.
            locked.delete()

            record_event(
                action="company.permanently_deleted",
                category=AuditCategory.CRM,
                user=request.user,
                request=request,
                entity_type="Client",
                entity_id=deleted_id,
                summary=f"Company #{deleted_id} '{deleted_name}' permanently deleted by superadmin.",
                metadata={"impact": final_impact},
            )

        return Response(
            {
                "detail": "Company permanently deleted.",
                "deleted_client_id": deleted_id,
                "impact": final_impact,
            }
        )
