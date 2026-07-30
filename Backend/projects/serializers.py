from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ["created_by"]
