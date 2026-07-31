from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsAdminRole, IsOwnerOrAdmin
from audit.mixins import AuditLogMixin
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
