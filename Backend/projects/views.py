from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(ModelViewSet):
    queryset = Project.objects.select_related("client", "created_by")
    serializer_class = ProjectSerializer
    permission_classes = [IsOwnerOrAdmin]
    filterset_fields = ["client", "type", "status", "start_date", "deadline", "created_by"]
    search_fields = ["title", "client__name", "notes"]
    ordering_fields = ["title", "type", "status", "budget", "start_date", "deadline", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
