from decimal import Decimal

from django.db.models import DecimalField, ProtectedError, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from accounts.permissions import DealPermission, IsAdminOrReadOnly
from audit.mixins import AuditLogMixin
from workforce.permissions import ShiftRequiredForWrite
from .models import Deal, Pipeline, SalesSettings, Stage
from .serializers import DealSerializer, PipelineSerializer, SalesSettingsSerializer, StageSerializer


def deal_value_total(queryset):
    return (
        queryset.aggregate(
            total=Coalesce(
                Sum("value"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        ).get("total")
        or Decimal("0.00")
    )


def commission_for(value, rate):
    return (value * rate) / Decimal("100")


class ProtectedDeleteMixin:
    protected_detail = "This record is still referenced and cannot be deleted."

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {"detail": self.protected_detail, "code": "protected"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PipelineViewSet(ProtectedDeleteMixin, ModelViewSet):
    queryset = Pipeline.objects.all()
    serializer_class = PipelineSerializer
    permission_classes = [IsAdminOrReadOnly]
    protected_detail = "This pipeline still has deals and cannot be deleted."
    filterset_fields = ["is_default"]
    search_fields = ["name"]
    ordering_fields = ["name", "is_default", "id"]
    ordering = ["name"]


class StageViewSet(ProtectedDeleteMixin, ModelViewSet):
    queryset = Stage.objects.select_related("pipeline")
    serializer_class = StageSerializer
    permission_classes = [IsAdminOrReadOnly]
    protected_detail = "This stage still has deals and cannot be deleted."
    filterset_fields = ["pipeline", "is_won", "is_lost"]
    search_fields = ["name", "pipeline__name"]
    ordering_fields = ["pipeline", "order", "name", "id"]
    ordering = ["pipeline", "order", "name"]


class DealViewSet(AuditLogMixin, ModelViewSet):
    queryset = Deal.objects.select_related("company", "owner", "pipeline", "stage")
    serializer_class = DealSerializer
    permission_classes = [DealPermission, ShiftRequiredForWrite]
    audit_track_fields = ["title", "value", "currency", "stage", "pipeline", "owner", "status", "expected_close_date"]
    filterset_fields = ["company", "pipeline", "stage", "owner", "status", "expected_close_date"]
    search_fields = ["title", "company__name", "contact_person", "owner__username", "notes"]
    ordering_fields = ["title", "value", "currency", "status", "expected_close_date", "created_at", "updated_at"]
    ordering = ["-updated_at", "-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("mine") == "true":
            queryset = queryset.filter(owner=self.request.user)
        return queryset

    def perform_create(self, serializer):
        # Sales users always own the deals they create; only admins may assign
        # an owner. Enforced server-side, not just in the UI.
        owner = serializer.validated_data.get("owner") if self.request.user.is_admin_role else self.request.user
        instance = serializer.save(owner=owner or self.request.user)
        self.audit_created(instance, summary=f"Deal '{instance.title}' created.")

    def perform_update(self, serializer):
        old = self.capture_old(serializer.instance)
        # Non-admins cannot reassign ownership of a deal, even via direct API.
        if self.request.user.is_admin_role:
            instance = serializer.save()
        else:
            instance = serializer.save(owner=serializer.instance.owner)
        self.audit_updated(instance, old, summary=f"Deal '{instance.title}' updated.")

    @action(detail=True, methods=["patch"], url_path="move")
    def move(self, request, pk=None):
        deal = self.get_object()
        stage_id = request.data.get("stage")
        if not stage_id:
            raise serializers.ValidationError({"stage": "This field is required."})

        try:
            stage = Stage.objects.get(pk=stage_id)
        except Stage.DoesNotExist:
            raise serializers.ValidationError({"stage": "Stage does not exist."})

        old_stage = deal.stage.name if deal.stage_id else None
        old_status = deal.status
        deal.pipeline = stage.pipeline
        deal.stage = stage
        deal.save()
        self.audit_action(
            deal, "deal.moved",
            f"Deal '{deal.title}' moved from {old_stage} to {stage.name}.",
            old_values={"stage": old_stage, "status": old_status},
            new_values={"stage": stage.name, "status": deal.status},
        )
        return Response(self.get_serializer(deal).data, status=status.HTTP_200_OK)


class CommissionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj = SalesSettings.load()
        rate = settings_obj.commission_rate_percent
        deals = Deal.objects.all() if request.user.is_admin_role else Deal.objects.filter(owner=request.user)
        won_value = deal_value_total(deals.filter(status=Deal.Status.WON))
        open_value = deal_value_total(deals.filter(status=Deal.Status.OPEN))
        return Response(
            {
                "commission_rate_percent": rate,
                "earned_commission": commission_for(won_value, rate),
                "potential_commission": commission_for(open_value, rate),
                "won_deal_value": won_value,
                "open_deal_value": open_value,
                "scope": "company" if request.user.is_admin_role else "personal",
            }
        )

    def patch(self, request):
        if not request.user.is_admin_role:
            return Response({"detail": "Only admins can update commission settings."}, status=status.HTTP_403_FORBIDDEN)
        settings_obj = SalesSettings.load()
        serializer = SalesSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "this_month")
        if period not in {"this_month", "all_time"}:
            raise serializers.ValidationError({"period": "Use this_month or all_time."})

        settings_obj = SalesSettings.load()
        rate = settings_obj.commission_rate_percent
        month_start = timezone.localdate().replace(day=1)
        reps = User.objects.filter(role=User.Role.SALES, is_active=True).order_by("username")
        rows = []

        for rep in reps:
            open_deals = Deal.objects.filter(owner=rep, status=Deal.Status.OPEN)
            won_deals = Deal.objects.filter(owner=rep, status=Deal.Status.WON)
            if period == "this_month":
                won_deals = won_deals.filter(closed_at__date__gte=month_start)

            open_value = deal_value_total(open_deals)
            won_value = deal_value_total(won_deals)
            potential_commission = commission_for(open_value, rate)
            earned_commission = commission_for(won_value, rate)
            display_name = rep.get_full_name() or rep.username
            initials = "".join(part[0] for part in display_name.split()[:2]).upper() or rep.username[:2].upper()
            rows.append(
                {
                    "rep_id": rep.id,
                    "rep_name": display_name,
                    "rep_initials": initials,
                    "is_current_user": rep.id == request.user.id,
                    "open_count": open_deals.count(),
                    "won_count": won_deals.count(),
                    "open_value": open_value,
                    "won_value": won_value,
                    "potential_commission": potential_commission,
                    "earned_commission": earned_commission,
                }
            )

        rows.sort(key=lambda row: (row["potential_commission"], row["earned_commission"], row["won_count"]), reverse=True)

        response_rows = []
        for index, row in enumerate(rows, start=1):
            base = {
                "rank": index,
                "rep_name": row["rep_name"],
                "rep_initials": row["rep_initials"],
                "is_current_user": row["is_current_user"],
            }
            if request.user.is_admin_role or row["is_current_user"]:
                base["rep_id"] = row["rep_id"]
                base.update(
                    {
                        "open_count": row["open_count"],
                        "won_count": row["won_count"],
                        "won_value": row["won_value"],
                        "potential_commission": row["potential_commission"],
                        "earned_commission": row["earned_commission"],
                    }
                )
                if request.user.is_admin_role:
                    base["open_value"] = row["open_value"]
            response_rows.append(base)

        return Response(
            {
                "scope": "company" if request.user.is_admin_role else "personal",
                "period": period,
                "commission_rate_percent": rate,
                "results": response_rows,
            }
        )
