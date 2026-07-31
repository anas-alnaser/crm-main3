import csv
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from accounts.permissions import IsAdminRole

from .models import AuditCategory, AuditEvent, AuditSource
from .serializers import AuditEventSerializer, TelemetryIngestSerializer
from .services import record_event

# Fields shown to employees so they understand what the system records.
PRIVACY_NOTICE = (
    "This workspace records meaningful business actions (logins, shift start/end, "
    "record changes, lead activity, and document generation) with who, when, and "
    "what changed. It never records your keystrokes, typed text, passwords, mouse "
    "movements, screenshots, or clipboard contents."
)


class AuditEventViewSet(ReadOnlyModelViewSet):
    """Admin-only, read-only audit viewer with rich filtering and CSV export."""

    queryset = AuditEvent.objects.select_related("user")
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    filterset_fields = ["user", "category", "action", "entity_type", "work_session", "source"]
    search_fields = ["summary", "action", "entity_type", "entity_id"]
    ordering_fields = ["created_at", "category", "action"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        date_from = params.get("from")
        date_to = params.get("to")
        if date_from:
            parsed = parse_datetime(date_from)
            if parsed:
                queryset = queryset.filter(created_at__gte=parsed)
        if date_to:
            parsed = parse_datetime(date_to)
            if parsed:
                queryset = queryset.filter(created_at__lte=parsed)
        return queryset

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        # Cap export size to keep it safe/streamable for an internal tool.
        rows = self.filter_queryset(self.get_queryset())[:10000]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(["created_at", "user", "category", "action", "entity_type", "entity_id", "summary", "ip_address", "source"])
        for event in rows:
            writer.writerow([
                event.created_at.isoformat(),
                event.user.username if event.user_id else "",
                event.category,
                event.action,
                event.entity_type,
                event.entity_id,
                event.summary,
                event.ip_address or "",
                event.source,
            ])
        record_event(
            action="audit.exported", category=AuditCategory.SECURITY, user=request.user, request=request,
            summary="Audit log exported to CSV.",
        )
        return response

    @action(detail=False, methods=["get"], url_path="privacy-notice", permission_classes=[IsAuthenticated])
    def privacy_notice(self, request):
        return Response({"notice": PRIVACY_NOTICE})


class FrontendTelemetryView(APIView):
    """Accepts a controlled whitelist of supplemental UI telemetry. Database-
    changing server events remain the authoritative record; this is best-effort
    and de-duplicated over a short window."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TelemetryIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # De-duplicate an identical event from the same user within 5 seconds.
        window_start = timezone.now() - timedelta(seconds=5)
        duplicate = AuditEvent.objects.filter(
            user=request.user,
            action=data["action"],
            entity_id=data.get("entity_id", ""),
            source=AuditSource.CLIENT,
            created_at__gte=window_start,
        ).exists()
        if duplicate:
            return Response({"recorded": False, "deduplicated": True})

        record_event(
            action=data["action"],
            category=AuditCategory.TELEMETRY,
            user=request.user,
            request=request,
            source=AuditSource.CLIENT,
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            metadata=data.get("metadata", {}),
            summary=f"UI: {data['action']}",
        )
        return Response({"recorded": True}, status=status.HTTP_201_CREATED)
