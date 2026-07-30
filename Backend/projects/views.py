from rest_framework.viewsets import ModelViewSet

from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(ModelViewSet):
    queryset = Project.objects.select_related("client")
    serializer_class = ProjectSerializer
    filterset_fields = ["client", "type", "status", "start_date", "deadline"]
    search_fields = ["title", "client__name", "notes"]
    ordering_fields = ["title", "type", "status", "budget", "start_date", "deadline", "created_at", "updated_at"]
    ordering = ["-created_at"]
