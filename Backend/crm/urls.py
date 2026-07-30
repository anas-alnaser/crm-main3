from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import CurrentUserView, ThrottledTokenObtainPairView, UserViewSet
from ai_commands.views import (
    AICommandCancelView,
    AICommandConfirmView,
    AICommandUndoView,
    AICommandView,
)
from activities.views import ActivityViewSet
from clients.views import ClientViewSet
from crm.views import DashboardStatsView, GlobalSearchView, HealthView
from meetings.views import MeetingViewSet
from projects.views import ProjectViewSet
from sales.views import CommissionView, DealViewSet, LeaderboardView, PipelineViewSet, StageViewSet
from tasks.views import TaskViewSet

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

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/login/", ThrottledTokenObtainPairView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("api/auth/me/", CurrentUserView.as_view(), name="current_user"),
    path("api/dashboard/stats/", DashboardStatsView.as_view(), name="dashboard_stats"),
    path("api/search/", GlobalSearchView.as_view(), name="global_search"),
    path("api/commission/", CommissionView.as_view(), name="commission"),
    path("api/leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("api/ai/command/", AICommandView.as_view(), name="ai_command"),
    path("api/ai/command/confirm/", AICommandConfirmView.as_view(), name="ai_command_confirm"),
    path("api/ai/command/cancel/", AICommandCancelView.as_view(), name="ai_command_cancel"),
    path("api/ai/command/undo/", AICommandUndoView.as_view(), name="ai_command_undo"),
    path("api/", include(router.urls)),
]
