from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from audit.mixins import AuditLogMixin
from workforce.permissions import ShiftRequiredForWrite
from .models import Meeting
from .serializers import MeetingSerializer


class MeetingPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_role:
            return True
        return obj.owner_id == request.user.id


class MeetingViewSet(AuditLogMixin, ModelViewSet):
    queryset = Meeting.objects.select_related("owner", "deal", "company")
    serializer_class = MeetingSerializer
    permission_classes = [MeetingPermission, ShiftRequiredForWrite]
    filterset_fields = ["status", "owner", "deal", "company"]
    search_fields = ["title", "description", "location", "company__name", "deal__title", "owner__username"]
    ordering_fields = ["start_datetime", "end_datetime", "status", "created_at", "updated_at"]
    ordering = ["start_datetime"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        scope = self.request.query_params.get("scope", "mine")

        if not user.is_admin_role or scope == "mine":
            queryset = queryset.filter(owner=user)

        from_datetime = self.request.query_params.get("from")
        to_datetime = self.request.query_params.get("to")
        if from_datetime:
            queryset = queryset.filter(start_datetime__gte=from_datetime)
        if to_datetime:
            queryset = queryset.filter(start_datetime__lte=to_datetime)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        owner = serializer.validated_data.get("owner") if user.is_admin_role else user
        instance = serializer.save(owner=owner or user)
        self.audit_created(instance, summary=f"Meeting '{instance.title}' created.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        if self.request.user.is_admin_role:
            instance = serializer.save()
        else:
            instance = serializer.save(owner=self.request.user)
        self.audit_updated(instance, old, summary=f"Meeting '{instance.title}' updated.")

    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request):
        now = timezone.now()
        upcoming_end = now + timedelta(days=7)
        queryset = self.get_queryset().filter(
            status=Meeting.Status.SCHEDULED,
            start_datetime__gte=now,
            start_datetime__lte=upcoming_end,
        )
        serializer = self.get_serializer(queryset.order_by("start_datetime"), many=True)
        return Response(serializer.data)
