from rest_framework.viewsets import ModelViewSet

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(ModelViewSet):
    queryset = Task.objects.select_related("client", "project", "deal")
    serializer_class = TaskSerializer
    filterset_fields = ["client", "project", "deal", "status", "due_date"]
    search_fields = ["title", "description", "client__name", "project__title", "deal__title"]
    ordering_fields = ["title", "status", "due_date", "created_at", "updated_at"]
    ordering = ["status", "due_date", "-created_at"]
