from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.models import User
from accounts.permissions import IsAdminRole
from audit.models import AuditCategory
from audit.services import record_event
from workforce.permissions import ShiftRequiredForWrite
from workforce.services import active_session

from .importer import ImportError_, parse_workbook
from .models import (
    SALES_SETTABLE_STATUSES,
    Lead,
    LeadContactAttempt,
    LeadImportBatch,
    LeadStatus,
)
from .serializers import (
    LeadContactAttemptSerializer,
    LeadImportBatchSerializer,
    LeadSerializer,
)
from .services import LeadError, convert_lead, find_matching_clients, mark_viewed, reopen_lead

ALLOWED_XLSX_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
    "application/zip",
    "",
}


class LeadViewSet(ModelViewSet):
    """Leads are scoped: admins see all, sales see only their assigned leads.

    Sales users cannot upload spreadsheets, cannot delete leads, and must be on
    shift to record contact attempts, change status, or convert (enforced by
    ``ShiftRequiredForWrite`` + shift checks in the services)."""

    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated, ShiftRequiredForWrite]
    filterset_fields = ["status", "assigned_to", "batch", "source"]
    search_fields = ["name", "original_phone", "normalized_phone", "notes"]
    ordering_fields = ["created_at", "updated_at", "follow_up_at", "status", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Lead.objects.select_related("assigned_to", "converted_client", "converted_deal")
        user = self.request.user
        if not user.is_admin_role:
            queryset = queryset.filter(assigned_to=user)
        if self.request.query_params.get("overdue") == "true":
            from django.utils import timezone

            queryset = queryset.filter(status=LeadStatus.FOLLOW_UP, follow_up_at__lt=timezone.now())
        return queryset

    def create(self, request, *args, **kwargs):
        # Leads enter the system through the import flow, not ad-hoc creation.
        if not request.user.is_admin_role:
            return Response({"detail": "Sales users cannot create leads directly.", "code": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        from .phone import normalize_phone

        normalized, country = normalize_phone(serializer.validated_data.get("original_phone", ""))
        lead = serializer.save(created_by=self.request.user, normalized_phone=normalized, country_context=country)
        record_event(
            action="lead.created", category=AuditCategory.LEAD, user=self.request.user, request=self.request,
            entity_type="Lead", entity_id=lead.pk, summary=f"Lead '{lead.name}' created manually.",
        )

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Leads cannot be deleted.", "code": "delete_disabled"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def retrieve(self, request, *args, **kwargs):
        lead = self.get_object()
        if not request.user.is_admin_role and lead.assigned_to_id == request.user.id:
            mark_viewed(lead, request.user, request=request)
        return Response(self.get_serializer(lead).data)

    def perform_update(self, serializer):
        # Guard status transitions; free-form fields (notes, follow_up) pass through.
        instance = serializer.instance
        new_status = serializer.validated_data.get("status", instance.status)
        user = self.request.user
        if new_status != instance.status:
            if new_status == LeadStatus.CONVERTED:
                raise serializers.ValidationError({"status": "Use the convert action to convert a lead."})
            if not user.is_admin_role and new_status not in SALES_SETTABLE_STATUSES:
                raise serializers.ValidationError({"status": "You cannot set this status."})
            if new_status == LeadStatus.NOT_INTERESTED:
                pass  # allowed; terminal, reopen requires admin
        old_status = instance.status
        lead = serializer.save()
        if new_status != old_status:
            record_event(
                action="lead.status_changed", category=AuditCategory.LEAD, user=user, request=self.request,
                entity_type="Lead", entity_id=lead.pk, summary=f"Lead '{lead.name}' status {old_status} -> {new_status}.",
                old_values={"status": old_status}, new_values={"status": new_status},
            )

    @action(detail=True, methods=["post"], url_path="contact")
    def contact(self, request, pk=None):
        lead = self.get_object()
        data = request.data
        method = data.get("method", LeadContactAttempt.Method.CALL)
        outcome = data.get("outcome")
        if outcome not in LeadContactAttempt.Outcome.values:
            return Response({"detail": "A valid outcome is required.", "code": "invalid_outcome"}, status=status.HTTP_400_BAD_REQUEST)
        resulting_status = data.get("resulting_status") or ""
        follow_up_at = data.get("follow_up_at") or None
        if resulting_status:
            if resulting_status not in LeadStatus.values or resulting_status == LeadStatus.CONVERTED:
                return Response({"detail": "Invalid resulting status.", "code": "invalid_status"}, status=status.HTTP_400_BAD_REQUEST)
            if not request.user.is_admin_role and resulting_status not in SALES_SETTABLE_STATUSES:
                return Response({"detail": "You cannot set this status.", "code": "forbidden_status"}, status=status.HTTP_403_FORBIDDEN)
            if resulting_status == LeadStatus.FOLLOW_UP and not follow_up_at:
                return Response({"detail": "A follow-up date/time is required for follow-up status.", "code": "follow_up_required"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            attempt = LeadContactAttempt.objects.create(
                lead=lead,
                employee=request.user,
                work_session=active_session(request.user),
                method=method,
                outcome=outcome,
                notes=data.get("notes", ""),
                follow_up_at=follow_up_at,
                resulting_status=resulting_status,
            )
            old_status = lead.status
            update_fields = ["updated_at"]
            if resulting_status:
                lead.status = resulting_status
                update_fields.append("status")
            if follow_up_at is not None:
                lead.follow_up_at = follow_up_at
                update_fields.append("follow_up_at")
            lead.save(update_fields=update_fields)

        record_event(
            action="lead.contact_attempt", category=AuditCategory.LEAD, user=request.user, request=request,
            work_session=attempt.work_session, entity_type="Lead", entity_id=lead.pk,
            summary=f"Contact attempt ({method}/{outcome}) on '{lead.name}'.",
            metadata={"method": method, "outcome": outcome},
            old_values={"status": old_status} if resulting_status else None,
            new_values={"status": resulting_status} if resulting_status else None,
        )
        return Response(
            {"attempt": LeadContactAttemptSerializer(attempt).data, "lead": self.get_serializer(lead).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="attempts")
    def attempts(self, request, pk=None):
        lead = self.get_object()
        attempts = lead.contact_attempts.select_related("employee")
        return Response(LeadContactAttemptSerializer(attempts, many=True).data)

    @action(detail=True, methods=["get"], url_path="match-candidates")
    def match_candidates(self, request, pk=None):
        lead = self.get_object()
        candidates = find_matching_clients(lead)
        return Response([{"id": c.id, "name": c.name, "phone": c.phone, "email": c.email} for c in candidates])

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        lead = self.get_object()
        data = request.data
        try:
            lead, client, deal = convert_lead(
                lead.pk,
                request.user,
                existing_client_id=data.get("existing_client_id") or None,
                create_deal=bool(data.get("create_deal")),
                deal_title=data.get("deal_title", ""),
                deal_value=data.get("deal_value") or None,
                deal_currency=data.get("deal_currency", "JOD"),
                reason=data.get("reason", ""),
                work_session=active_session(request.user),
                request=request,
            )
        except LeadError as exc:
            code = status.HTTP_409_CONFLICT if exc.code in {"already_converted", "terminal"} else status.HTTP_400_BAD_REQUEST
            return Response({"detail": exc.message, "code": exc.code}, status=code)
        return Response(
            {
                "lead": self.get_serializer(lead).data,
                "client": {"id": client.id, "name": client.name},
                "deal": {"id": deal.id, "title": deal.title} if deal else None,
            }
        )

    @action(detail=True, methods=["post"], url_path="reopen", permission_classes=[IsAuthenticated, IsAdminRole])
    def reopen(self, request, pk=None):
        lead = self.get_object()
        try:
            reopen_lead(lead, request.user, request.data.get("reason", ""), request=request)
        except LeadError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["patch"], url_path="assign", permission_classes=[IsAuthenticated, IsAdminRole])
    def assign(self, request, pk=None):
        lead = self.get_object()
        assignee_id = request.data.get("assigned_to")
        assignee = User.objects.filter(pk=assignee_id).first() if assignee_id else None
        if assignee_id and assignee is None:
            return Response({"detail": "User not found.", "code": "not_found"}, status=status.HTTP_400_BAD_REQUEST)
        old = lead.assigned_to_id
        lead.assigned_to = assignee
        lead.save(update_fields=["assigned_to", "updated_at"])
        record_event(
            action="lead.assigned", category=AuditCategory.LEAD, user=request.user, request=request,
            entity_type="Lead", entity_id=lead.pk,
            summary=f"Lead '{lead.name}' assigned to {assignee.username if assignee else 'nobody'}.",
            old_values={"assigned_to": old}, new_values={"assigned_to": assignee.id if assignee else None},
        )
        return Response(self.get_serializer(lead).data)


class LeadImportBatchViewSet(ReadOnlyModelViewSet):
    """Admin-only import history + the upload endpoint."""

    queryset = LeadImportBatch.objects.select_related("uploaded_by", "assigned_to")
    serializer_class = LeadImportBatchSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["status", "assigned_to", "uploaded_by"]
    ordering_fields = ["uploaded_at"]
    ordering = ["-uploaded_at"]

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        from django.conf import settings

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded.", "code": "no_file"}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith(".xlsx"):
            return Response({"detail": "Only .xlsx files are supported.", "code": "bad_extension"}, status=status.HTTP_400_BAD_REQUEST)
        if upload.content_type not in ALLOWED_XLSX_TYPES:
            return Response({"detail": f"Unexpected file type: {upload.content_type}.", "code": "bad_type"}, status=status.HTTP_400_BAD_REQUEST)
        max_bytes = getattr(settings, "LEAD_IMPORT_MAX_BYTES", 5 * 1024 * 1024)
        if upload.size > max_bytes:
            return Response({"detail": f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.", "code": "too_large"}, status=status.HTTP_400_BAD_REQUEST)

        preview = str(request.data.get("preview", "")).lower() == "true"
        assignee_id = request.data.get("assigned_to") or None
        assignee = User.objects.filter(pk=assignee_id).first() if assignee_id else None
        if assignee_id and assignee is None:
            return Response({"detail": "Assignee not found.", "code": "assignee_not_found"}, status=status.HTTP_400_BAD_REQUEST)
        source = request.data.get("source", "")

        try:
            result = parse_workbook(upload)
        except ImportError_ as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)

        if preview:
            return Response({"preview": True, **result.summary()})

        with transaction.atomic():
            batch = LeadImportBatch.objects.create(
                source=source,
                original_filename=upload.name[:255],
                uploaded_by=request.user,
                assigned_to=assignee,
                status=LeadImportBatch.Status.COMPLETED,
                total_rows=result.total_rows,
                imported_count=len(result.imported),
                invalid_count=len(result.invalid),
                duplicate_count=len(result.duplicates),
                skipped_count=len(result.skipped),
                assigned_count=len(result.imported) if assignee else 0,
                validation_result=result.summary(),
            )
            leads = [
                Lead(
                    batch=batch,
                    name=row["name"],
                    original_phone=row["original_phone"],
                    normalized_phone=row["normalized_phone"],
                    country_context=row["country_context"],
                    source=source,
                    assigned_to=assignee,
                    created_by=request.user,
                )
                for row in result.imported
            ]
            Lead.objects.bulk_create(leads, batch_size=500)

        record_event(
            action="lead.import", category=AuditCategory.LEAD, user=request.user, request=request,
            entity_type="LeadImportBatch", entity_id=batch.pk,
            summary=f"Imported {batch.imported_count} leads from '{batch.original_filename}'"
                    + (f", assigned to {assignee.username}" if assignee else "") + ".",
            metadata=result.counts(),
        )
        return Response(self.get_serializer(batch).data, status=status.HTTP_201_CREATED)
