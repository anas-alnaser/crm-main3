from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(ModelViewSet):
    queryset = Task.objects.select_related("client", "project", "deal", "created_by")
    serializer_class = TaskSerializer
    permission_classes = [IsOwnerOrAdmin]
    filterset_fields = ["client", "project", "deal", "status", "due_date", "created_by"]
    search_fields = ["title", "description", "client__name", "project__title", "deal__title"]
    ordering_fields = ["title", "status", "due_date", "created_at", "updated_at"]
    ordering = ["status", "due_date", "-created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
