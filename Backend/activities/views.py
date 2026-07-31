from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from audit.mixins import AuditLogMixin
from workforce.permissions import ShiftRequiredForWrite
from .models import Activity
from .serializers import ActivitySerializer


class ActivityViewSet(AuditLogMixin, ModelViewSet):
    queryset = Activity.objects.select_related("client", "project", "deal", "created_by")
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin, ShiftRequiredForWrite]
    filterset_fields = ["type", "client", "project", "deal", "created_at", "created_by"]
    search_fields = ["content", "client__name", "project__title", "deal__title"]
    ordering_fields = ["type", "created_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self.audit_created(instance, summary=f"Activity ({instance.type}) logged.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        instance = serializer.save()
        self.audit_updated(instance, old, summary=f"Activity #{instance.pk} updated.")
