from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from audit.mixins import AuditLogMixin
from workforce.permissions import ShiftRequiredForWrite
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(AuditLogMixin, ModelViewSet):
    queryset = Task.objects.select_related("client", "project", "deal", "created_by")
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin, ShiftRequiredForWrite]
    filterset_fields = ["client", "project", "deal", "status", "due_date", "created_by"]
    search_fields = ["title", "description", "client__name", "project__title", "deal__title"]
    ordering_fields = ["title", "status", "due_date", "created_at", "updated_at"]
    ordering = ["status", "due_date", "-created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self.audit_created(instance, summary=f"Task '{instance.title}' created.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        instance = serializer.save()
        self.audit_updated(instance, old, summary=f"Task '{instance.title}' updated.")
