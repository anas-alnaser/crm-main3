import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.permissions import IsAdminRole

from . import services
from .models import EmployeeWorkPolicy, WorkPolicyException, WorkSession
from .scheduler_auth import SchedulerAuthError, authenticate_scheduler
from .serializers import (
    EmployeeWorkPolicySerializer,
    WorkPolicyExceptionSerializer,
    WorkSessionSerializer,
    humanize_seconds,
)
from .services import ShiftError, close_stale_sessions

logger = logging.getLogger("workforce")

# SchedulerAuthError.code -> HTTP status for the internal reconcile endpoint.
_SCHEDULER_ERROR_STATUS = {
    "missing_token": status.HTTP_401_UNAUTHORIZED,
    "invalid_token": status.HTTP_403_FORBIDDEN,
    "not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _shift_error_response(exc: ShiftError):
    return Response(
        {"detail": exc.message, "code": exc.code, **({"context": exc.extra} if exc.extra else {})},
        status=status.HTTP_409_CONFLICT,
    )


def _format_totals(totals: dict) -> dict:
    return {
        "date": totals["date"],
        "credited_seconds": totals["credited_seconds"],
        "credited_display": humanize_seconds(totals["credited_seconds"]),
        "target_seconds": totals["target_seconds"],
        "target_display": humanize_seconds(totals["target_seconds"]),
        "remaining_seconds": totals["remaining_seconds"],
        "remaining_display": humanize_seconds(totals["remaining_seconds"]),
        "overtime_seconds": totals["overtime_seconds"],
        "overtime_display": humanize_seconds(totals["overtime_seconds"]),
        "session_count": totals["session_count"],
    }


def _serialize_status(request, data: dict) -> dict:
    policy = data.get("policy")
    session = data.get("session")
    window = data.get("window")
    payload = {
        "shift_tracking_required": data["shift_tracking_required"],
        "on_shift": data["on_shift"],
        "server_time": data["server_time"],
        "local_time": data["local_time"],
        "today": data["today"],
        "reason": data.get("reason", ""),
        "can_start": data.get("can_start", False),
        "totals": _format_totals(data["totals"]),
    }
    if policy is not None:
        payload["policy"] = {
            "timezone": policy.timezone,
            "earliest_start_time": policy.earliest_start_time.strftime("%H:%M"),
            "latest_end_time": policy.latest_end_time.strftime("%H:%M"),
            "daily_target_minutes": policy.daily_target_minutes,
            "working_days": policy.working_days,
            "working_day_labels": policy.working_day_labels(),
            "overtime_allowed": policy.overtime_allowed,
        }
    if window is not None:
        payload["window"] = {
            "is_working_day": window.is_working_day,
            "start_time": window.start_time.strftime("%H:%M"),
            "end_time": window.end_time.strftime("%H:%M"),
        }
    if session is not None:
        payload["session"] = {
            "id": session.id,
            "started_at": session.started_at,
            "last_activity_at": session.last_activity_at,
            "work_date": session.work_date,
            "current_session_seconds": data.get("current_session_seconds", 0),
            "current_session_display": humanize_seconds(data.get("current_session_seconds", 0)),
        }
    # Surface the most recent automatic closure today so the UI can explain it.
    last_auto = (
        WorkSession.objects.filter(employee=request.user, auto_closed=True, work_date=data["today"])
        .order_by("-ended_at")
        .first()
    )
    if last_auto is not None:
        payload["last_auto_closure"] = {
            "reason": last_auto.closing_reason,
            "reason_display": last_auto.get_closing_reason_display(),
            "ended_at": last_auto.ended_at,
        }
    return payload


class ShiftStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = services.shift_status(request.user)
        return Response(_serialize_status(request, data))


class ShiftStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            services.start_shift(request.user, request=request)
        except ShiftError as exc:
            return _shift_error_response(exc)
        return Response(_serialize_status(request, services.shift_status(request.user)), status=status.HTTP_201_CREATED)


class ShiftEndPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            preview = services.end_shift_preview(request.user)
        except ShiftError as exc:
            return _shift_error_response(exc)
        message = (
            f"Hi {preview['employee_name']}, you have worked for "
            f"{humanize_seconds(preview['credited_seconds_today'])} today. "
            "Are you sure you want to end this work session?"
        )
        return Response(
            {
                "employee_name": preview["employee_name"],
                "message": message,
                "current_session_seconds": preview["current_session_seconds"],
                "current_session_display": humanize_seconds(preview["current_session_seconds"]),
                "credited_seconds_today": preview["credited_seconds_today"],
                "credited_display_today": humanize_seconds(preview["credited_seconds_today"]),
                "target_seconds": preview["target_seconds"],
                "target_display": humanize_seconds(preview["target_seconds"]),
                "remaining_seconds": preview["remaining_seconds"],
                "remaining_display": humanize_seconds(preview["remaining_seconds"]),
                "overtime_seconds": preview["overtime_seconds"],
                "overtime_display": humanize_seconds(preview["overtime_seconds"]),
                "session_count": preview["session_count"],
            }
        )


class ShiftEndView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            services.end_shift(request.user, request=request)
        except ShiftError as exc:
            return _shift_error_response(exc)
        return Response(_serialize_status(request, services.shift_status(request.user)))


class ShiftHeartbeatView(APIView):
    """Throttled presence heartbeat. Carries no keystroke/mouse content — only
    the fact that the user was genuinely active."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = services.record_heartbeat(request.user, request=request)
        if session is None:
            return Response({"on_shift": False})
        return Response(
            {
                "on_shift": session.is_active,
                "session_id": session.id if session.is_active else None,
                "last_activity_at": session.last_activity_at,
                "closing_reason": session.closing_reason or None,
            }
        )


class EmployeeWorkPolicyViewSet(ModelViewSet):
    queryset = EmployeeWorkPolicy.objects.select_related("user", "last_modified_by")
    serializer_class = EmployeeWorkPolicySerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["is_active", "shift_tracking_required", "user"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    ordering_fields = ["user__username", "created_at", "updated_at"]

    def perform_create(self, serializer):
        policy = serializer.save(last_modified_by=self.request.user)
        self._audit(policy, "policy.created")

    def perform_update(self, serializer):
        policy = serializer.save(last_modified_by=self.request.user)
        self._audit(policy, "policy.updated")

    def _audit(self, policy, action_code):
        from audit.models import AuditCategory
        from audit.services import record_event

        record_event(
            action=action_code,
            category=AuditCategory.POLICY,
            user=self.request.user,
            request=self.request,
            entity_type="EmployeeWorkPolicy",
            entity_id=policy.pk,
            summary=f"Work policy for {policy.user.username} {action_code.split('.')[-1]}.",
            new_values={
                "shift_tracking_required": policy.shift_tracking_required,
                "is_active": policy.is_active,
                "daily_target_minutes": policy.daily_target_minutes,
                "working_days": policy.working_days,
            },
        )


class WorkPolicyExceptionViewSet(ModelViewSet):
    queryset = WorkPolicyException.objects.select_related("policy", "approved_by")
    serializer_class = WorkPolicyExceptionSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["policy", "exception_type", "date"]
    ordering_fields = ["date", "created_at"]

    def perform_create(self, serializer):
        serializer.save(approved_by=self.request.user)


class WorkSessionViewSet(ReadOnlyModelViewSet):
    queryset = WorkSession.objects.select_related("employee")
    serializer_class = WorkSessionSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["employee", "work_date", "closing_reason", "auto_closed"]
    ordering_fields = ["started_at", "ended_at", "work_date", "credited_seconds"]
    ordering = ["-started_at"]

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        session = self.get_object()
        services.admin_close_session(session, actor=request.user, request=request)
        session.refresh_from_db()
        return Response(self.get_serializer(session).data)


class WorkforceDashboardView(APIView):
    """Admin-only workforce & performance dashboard for a single employee."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        from accounts.models import User

        from . import metrics

        employee_id = request.query_params.get("employee")
        if not employee_id:
            return Response({"detail": "employee is required.", "code": "employee_required"}, status=status.HTTP_400_BAD_REQUEST)
        employee = User.objects.filter(pk=employee_id).first()
        if employee is None:
            return Response({"detail": "Employee not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        start, end = metrics.resolve_period(request.query_params)
        return Response(metrics.employee_dashboard(employee, start, end))


class WorkforceEmployeesView(APIView):
    """Admin-only: employees that have a work policy (for the dashboard picker)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        from accounts.serializers import UserSerializer

        policies = EmployeeWorkPolicy.objects.select_related("user").order_by("user__username")
        users = [p.user for p in policies]
        return Response(UserSerializer(users, many=True).data)


class SchedulerReconcileView(APIView):
    """Internal endpoint that closes stale work sessions on the server clock.

    Called once a minute by a Google Cloud Scheduler job whose request carries a
    verified OIDC token for the scheduler service account (see
    ``workforce.scheduler_auth``). This replaces an always-running scheduler
    process: the work is a single idempotent, concurrency-safe sweep.

    The endpoint takes **no input** — it never reads a user id or timestamp from
    the request, and always reconciles against ``timezone.now()`` for every open
    session. Normal users, admins in the browser, and anonymous callers cannot
    authenticate and are rejected.
    """

    # Governed entirely by the OIDC gate below — DRF's JWT auth, permissions, and
    # throttles do not apply (a user's SimpleJWT must never authorise this).
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    def post(self, request):
        try:
            authenticate_scheduler(request)
        except SchedulerAuthError as exc:
            if exc.code != "missing_token":
                # Missing token is routine noise; log genuine rejections.
                logger.warning("Scheduler reconcile rejected: %s", exc.code)
            return Response(
                {"detail": exc.message, "code": exc.code},
                status=_SCHEDULER_ERROR_STATUS.get(exc.code, status.HTTP_403_FORBIDDEN),
            )

        # Deliberately ignores request body/query entirely.
        result = close_stale_sessions()
        return Response(
            {
                "status": "ok",
                "inspected": result["inspected"],
                "closed": result["closed"],
                "at": result["at"],
            }
        )
