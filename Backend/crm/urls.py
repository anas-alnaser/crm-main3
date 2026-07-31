from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import CurrentUserView, LogoutView, ThrottledTokenObtainPairView, UserViewSet
from activities.views import ActivityViewSet
from ai_commands.views import (
    AICommandCancelView,
    AICommandConfirmView,
    AICommandUndoView,
    AICommandView,
)
from audit.views import AuditEventViewSet, FrontendTelemetryView
from branding.views import (
    BrandProfileViewSet,
    GeneratedDocumentViewSet,
    LegalEntityViewSet,
    SignatoryViewSet,
)
from clients.views import ClientViewSet
from crm.views import DashboardStatsView, GlobalSearchView, HealthView
from leads.views import LeadImportBatchViewSet, LeadViewSet
from meetings.views import MeetingViewSet
from projects.views import ProjectViewSet
from sales.views import CommissionView, DealViewSet, LeaderboardView, PipelineViewSet, StageViewSet
from tasks.views import TaskViewSet
from workforce.views import (
    EmployeeWorkPolicyViewSet,
    ShiftEndPreviewView,
    ShiftEndView,
    ShiftHeartbeatView,
    ShiftStartView,
    ShiftStatusView,
    WorkforceDashboardView,
    WorkforceEmployeesView,
    WorkPolicyExceptionViewSet,
    WorkSessionViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("clients", ClientViewSet)
router.register("projects", ProjectViewSet)
router.register("pipelines", PipelineViewSet)
router.register("stages", StageViewSet)
router.register("deals", DealViewSet)
router.register("tasks", TaskViewSet)
router.register("activities", ActivityViewSet)
router.register("meetings", MeetingViewSet)
# Workforce
router.register("work-policies", EmployeeWorkPolicyViewSet)
router.register("work-policy-exceptions", WorkPolicyExceptionViewSet)
router.register("work-sessions", WorkSessionViewSet)
# Leads
router.register("leads", LeadViewSet, basename="lead")
router.register("lead-imports", LeadImportBatchViewSet)
# Audit
router.register("audit-events", AuditEventViewSet)
# Branding
router.register("legal-entities", LegalEntityViewSet)
router.register("signatories", SignatoryViewSet)
router.register("brands", BrandProfileViewSet)
router.register("documents", GeneratedDocumentViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/login/", ThrottledTokenObtainPairView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("api/auth/me/", CurrentUserView.as_view(), name="current_user"),
    path("api/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/dashboard/stats/", DashboardStatsView.as_view(), name="dashboard_stats"),
    path("api/search/", GlobalSearchView.as_view(), name="global_search"),
    path("api/commission/", CommissionView.as_view(), name="commission"),
    path("api/leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("api/ai/command/", AICommandView.as_view(), name="ai_command"),
    path("api/ai/command/confirm/", AICommandConfirmView.as_view(), name="ai_command_confirm"),
    path("api/ai/command/cancel/", AICommandCancelView.as_view(), name="ai_command_cancel"),
    path("api/ai/command/undo/", AICommandUndoView.as_view(), name="ai_command_undo"),
    # Workforce / shift
    path("api/workforce/shift/status/", ShiftStatusView.as_view(), name="shift_status"),
    path("api/workforce/shift/start/", ShiftStartView.as_view(), name="shift_start"),
    path("api/workforce/shift/end/preview/", ShiftEndPreviewView.as_view(), name="shift_end_preview"),
    path("api/workforce/shift/end/", ShiftEndView.as_view(), name="shift_end"),
    path("api/workforce/shift/heartbeat/", ShiftHeartbeatView.as_view(), name="shift_heartbeat"),
    path("api/workforce/dashboard/", WorkforceDashboardView.as_view(), name="workforce_dashboard"),
    path("api/workforce/employees/", WorkforceEmployeesView.as_view(), name="workforce_employees"),
    # Audit telemetry
    path("api/telemetry/", FrontendTelemetryView.as_view(), name="frontend_telemetry"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
