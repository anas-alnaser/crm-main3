from decimal import Decimal

from django.db import connection
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from activities.models import Activity
from clients.models import Client
from meetings.models import Meeting
from sales.models import Deal
from tasks.models import Task


class HealthView(APIView):
    """Unauthenticated liveness/readiness probe for load balancers and Docker."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # pragma: no cover - defensive
            db_ok = False
        return Response({"status": "ok" if db_ok else "degraded", "database": db_ok})


def _visible_deals(user):
    deals = Deal.objects.select_related("company", "owner")
    if hasattr(Deal, "is_archived"):
        deals = deals.filter(is_archived=False)
    return deals


class GlobalSearchView(APIView):
    """Single authenticated global search across the resources a user may read.

    Applies the same role-based masking as the list/detail endpoints so
    restricted values (e.g. deal amounts owned by others) are never exposed.
    """

    RESULT_LIMIT = 8

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"query": query, "results": {"clients": [], "deals": [], "tasks": [], "meetings": [], "activities": []}})

        user = request.user
        is_admin = user.is_admin_role
        limit = self.RESULT_LIMIT

        clients = Client.objects.all()
        if hasattr(Client, "is_archived"):
            clients = clients.filter(is_archived=False)
        clients = clients.filter(
            Q(name__icontains=query)
            | Q(contact_person__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )[:limit]

        deals = _visible_deals(user).filter(
            Q(title__icontains=query) | Q(company__name__icontains=query) | Q(contact_person__icontains=query)
        )[:limit]

        tasks = Task.objects.select_related("client", "deal").filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )[:limit]

        meetings = Meeting.objects.select_related("company", "deal", "owner")
        if not is_admin:
            meetings = meetings.filter(owner=user)
        meetings = meetings.filter(
            Q(title__icontains=query) | Q(location__icontains=query) | Q(company__name__icontains=query)
        )[:limit]

        activities = Activity.objects.select_related("client", "deal").filter(Q(content__icontains=query))[:limit]

        def deal_value(deal):
            if is_admin or deal.owner_id == user.id:
                return str(deal.value) if deal.value is not None else None
            return None

        return Response(
            {
                "query": query,
                "results": {
                    "clients": [
                        {"id": c.id, "name": c.name, "contact_person": c.contact_person, "email": c.email, "status": c.status}
                        for c in clients
                    ],
                    "deals": [
                        {
                            "id": d.id,
                            "title": d.title,
                            "company_name": d.company.name if d.company_id else None,
                            "owner_username": d.owner.username if d.owner_id else None,
                            "status": d.status,
                            "value": deal_value(d),
                        }
                        for d in deals
                    ],
                    "tasks": [
                        {"id": t.id, "title": t.title, "status": t.status, "due_date": t.due_date, "client_name": t.client.name if t.client_id else None, "deal_title": t.deal.title if t.deal_id else None}
                        for t in tasks
                    ],
                    "meetings": [
                        {"id": m.id, "title": m.title, "status": m.status, "start_datetime": m.start_datetime, "company_name": m.company.name if m.company_id else None, "deal_title": m.deal.title if m.deal_id else None}
                        for m in meetings
                    ],
                    "activities": [
                        {"id": a.id, "type": a.type, "content": a.content, "created_at": a.created_at, "client_name": a.client.name if a.client_id else None, "deal_title": a.deal.title if a.deal_id else None}
                        for a in activities
                    ],
                },
            }
        )


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
