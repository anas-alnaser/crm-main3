from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models import Deal


class DashboardStatsView(APIView):
    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        deals = Deal.objects.all()
        if not request.user.is_admin_role:
            deals = deals.filter(owner=request.user)

        won_count = deals.filter(status=Deal.Status.WON).count()
        lost_count = deals.filter(status=Deal.Status.LOST).count()
        closed_count = won_count + lost_count
        win_rate = round((won_count / closed_count) * 100, 2) if closed_count else 0

        total_pipeline_value = (
            deals.filter(status=Deal.Status.OPEN)
            .aggregate(
                total=Coalesce(
                    Sum("value"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .get("total")
            or 0
        )
        value_by_stage = list(
            deals.values("stage", "stage__name")
            .annotate(
                count=Count("id"),
                value=Coalesce(
                    Sum("value"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .order_by("stage__order", "stage__name")
        )

        return Response(
            {
                "scope": "company" if request.user.is_admin_role else "personal",
                "total_open_deals": deals.filter(status=Deal.Status.OPEN).count(),
                "total_pipeline_value": total_pipeline_value,
                "deals_won_this_month": deals.filter(status=Deal.Status.WON, updated_at__date__gte=month_start).count(),
                "win_rate": win_rate,
                "value_by_stage": [
                    {
                        "stage_id": row["stage"],
                        "stage_name": row["stage__name"],
                        "count": row["count"],
                        "value": row["value"],
                    }
                    for row in value_by_stage
                ],
            }
        )
