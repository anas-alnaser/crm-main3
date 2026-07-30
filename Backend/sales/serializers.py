from rest_framework import serializers

from .models import Deal, Pipeline, SalesSettings, Stage


def calculate_commission(value, rate):
    if value is None:
        return None
    return (value * rate) / 100


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = "__all__"


class StageSerializer(serializers.ModelSerializer):
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)

    class Meta:
        model = Stage
        fields = "__all__"


class DealSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    commission = serializers.SerializerMethodField()

    class Meta:
        model = Deal
        fields = "__all__"
        read_only_fields = ["status"]
        extra_kwargs = {"owner": {"required": False}}

    def get_commission(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated and not request.user.is_admin_role and obj.owner_id != request.user.id:
            return None
        if obj.value is None:
            return None
        rate = SalesSettings.load().commission_rate_percent
        return calculate_commission(obj.value, rate)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.is_authenticated and not request.user.is_admin_role and instance.owner_id != request.user.id:
            data["value"] = None
            data["commission"] = None
        return data

    def validate(self, attrs):
        pipeline = attrs.get("pipeline") or getattr(self.instance, "pipeline", None)
        stage = attrs.get("stage") or getattr(self.instance, "stage", None)
        if pipeline and stage and stage.pipeline_id != pipeline.id:
            raise serializers.ValidationError({"stage": "Stage must belong to the selected pipeline."})
        return attrs


class SalesSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesSettings
        fields = ["commission_rate_percent", "updated_at"]
        read_only_fields = ["updated_at"]
