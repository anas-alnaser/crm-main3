from rest_framework import serializers

from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    deal_title = serializers.CharField(source="deal.title", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ["created_by"]
