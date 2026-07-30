from rest_framework import serializers

from .models import Meeting


class MeetingSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    deal_title = serializers.CharField(source="deal.title", read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Meeting
        fields = "__all__"
        extra_kwargs = {"owner": {"required": False}}

    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.username

    def validate(self, attrs):
        start_datetime = attrs.get("start_datetime") or getattr(self.instance, "start_datetime", None)
        end_datetime = attrs.get("end_datetime") or getattr(self.instance, "end_datetime", None)
        deal = attrs.get("deal") or getattr(self.instance, "deal", None)
        company = attrs.get("company") or getattr(self.instance, "company", None)

        if start_datetime and end_datetime and end_datetime <= start_datetime:
            raise serializers.ValidationError({"end_datetime": "End time must be after the start time."})
        if deal and company and deal.company_id != company.id:
            raise serializers.ValidationError({"company": "Company must match the selected deal."})
        return attrs
