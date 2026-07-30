from rest_framework.viewsets import ModelViewSet

from .models import Activity
from .serializers import ActivitySerializer


class ActivityViewSet(ModelViewSet):
    queryset = Activity.objects.select_related("client", "project", "deal")
    serializer_class = ActivitySerializer
    filterset_fields = ["type", "client", "project", "deal", "created_at"]
    search_fields = ["content", "client__name", "project__title", "deal__title"]
    ordering_fields = ["type", "created_at"]
    ordering = ["-created_at"]
