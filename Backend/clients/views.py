from rest_framework.viewsets import ModelViewSet

from .models import Client
from .serializers import ClientSerializer


class ClientViewSet(ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filterset_fields = ["status", "country"]
    search_fields = ["name", "contact_person", "email", "phone", "country", "notes"]
    ordering_fields = ["name", "country", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]
