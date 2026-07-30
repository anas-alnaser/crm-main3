from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsOwnerOrAdmin
from .models import Activity
from .serializers import ActivitySerializer


class ActivityViewSet(ModelViewSet):
    queryset = Activity.objects.select_related("client", "project", "deal", "created_by")
    serializer_class = ActivitySerializer
    permission_classes = [IsOwnerOrAdmin]
    filterset_fields = ["type", "client", "project", "deal", "created_at", "created_by"]
    search_fields = ["content", "client__name", "project__title", "deal__title"]
    ordering_fields = ["type", "created_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
