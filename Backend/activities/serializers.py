from rest_framework import serializers

from .models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    deal_title = serializers.CharField(source="deal.title", read_only=True)

    class Meta:
        model = Activity
        fields = "__all__"
