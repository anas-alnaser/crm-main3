from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from audit.mixins import AuditLogMixin
from workforce.permissions import ShiftRequiredForWrite
from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(AuditLogMixin, ModelViewSet):
    queryset = Project.objects.select_related("client", "created_by")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin, ShiftRequiredForWrite]
    filterset_fields = ["client", "type", "status", "start_date", "deadline", "created_by"]
    search_fields = ["title", "client__name", "notes"]
    ordering_fields = ["title", "type", "status", "budget", "start_date", "deadline", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self.audit_created(instance, summary=f"Project '{instance.title}' created.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        instance = serializer.save()
        self.audit_updated(instance, old, summary=f"Project '{instance.title}' updated.")
