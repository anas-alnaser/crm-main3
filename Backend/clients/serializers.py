from rest_framework import serializers

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Client
        fields = "__all__"
        read_only_fields = ["created_by", "is_archived", "archived_at", "archived_by"]
