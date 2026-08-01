from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.views import TokenObtainPairView

from audit.models import AuditCategory
from audit.services import record_event
from crm import danger
from crm.throttling import DangerZoneThrottle, LoginRateThrottle
from .permissions import IsAdminRole, IsSuperAdmin, is_super_admin
from .models import User
from .serializers import (
    PasswordResetSerializer,
    UserManagementSerializer,
    UserSerializer,
)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login endpoint with IP-based throttling to slow brute-force attempts.

    Records a server-authoritative audit event for successful and failed logins
    (the failure event stores only the attempted username, never the password)."""

    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        username = str(request.data.get("username", ""))[:150]
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            user = User.objects.filter(username=username).first()
            record_event(
                action="auth.login_success", category=AuditCategory.AUTH, user=user, request=request,
                entity_type="User", entity_id=getattr(user, "pk", ""),
                summary=f"Login success for {username}.",
            )
        else:
            record_event(
                action="auth.login_failed", category=AuditCategory.AUTH, request=request,
                summary=f"Failed login attempt for username '{username}'.",
                metadata={"username": username},
            )
        return response


class CurrentUserView(RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """Stateless-JWT logout: the client discards tokens; we record the event."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        record_event(
            action="auth.logout", category=AuditCategory.AUTH, user=request.user, request=request,
            entity_type="User", entity_id=request.user.pk, summary=f"Logout for {request.user.username}.",
        )
        return Response({"detail": "Logged out."})


def active_admin_count(exclude_id=None):
    """Count users who currently have admin-level access."""
    queryset = User.objects.filter(is_active=True).filter(
        Q(role=User.Role.ADMIN) | Q(is_superuser=True) | Q(is_staff=True)
    )
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.count()


class UserViewSet(ModelViewSet):
    queryset = User.objects.order_by("username")
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdminRole]
    search_fields = ["username", "email", "first_name", "last_name"]
    filterset_fields = ["role", "is_active"]
    ordering_fields = ["username", "email", "role", "is_active", "id"]

    def perform_create(self, serializer):
        user = serializer.save()
        record_event(
            action="user.created", category=AuditCategory.USER, user=self.request.user, request=self.request,
            entity_type="User", entity_id=user.pk, summary=f"User '{user.username}' created with role {user.role}.",
            new_values={"username": user.username, "role": user.role},
        )

    def destroy(self, request, *args, **kwargs):
        # Hard deletion is disabled through the CRM API to preserve ownership
        # and reporting history. Use deactivate/reactivate instead.
        return Response(
            {"detail": "Users cannot be deleted. Deactivate the user instead.", "code": "delete_disabled"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["patch"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.id == request.user.id:
            return Response(
                {"detail": "You cannot deactivate your own account.", "code": "self_deactivate"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_admin_role and active_admin_count(exclude_id=user.id) == 0:
            return Response(
                {"detail": "You cannot deactivate the last active admin.", "code": "last_admin"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
            record_event(
                action="user.deactivated", category=AuditCategory.USER, user=request.user, request=request,
                entity_type="User", entity_id=user.pk, summary=f"User '{user.username}' deactivated.",
            )
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["patch"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
            record_event(
                action="user.reactivated", category=AuditCategory.USER, user=request.user, request=request,
                entity_type="User", entity_id=user.pk, summary=f"User '{user.username}' reactivated.",
            )
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["temp_password"])
        user.save(update_fields=["password"])
        # Never echo the password back.
        return Response({"detail": "Password reset.", "id": user.id})

    # -- Superadmin-only permanent deletion --------------------------------
    # Deactivate/Reactivate above remain the normal behaviour. A superadmin may
    # permanently delete *another* user (never themselves) after re-authenticating.
    # Ownership references are inspected first: SET_NULL fields are cleared by the
    # ORM; PROTECT references (owned deals, meetings, AI-command logs) block the
    # deletion until they are reassigned, so a ProtectedError can never occur.

    @staticmethod
    def _ownership_impact(user) -> dict:
        return {
            # PROTECT — must be reassigned before the user can be deleted.
            "owned_deals": user.deals.count(),
            "owned_meetings": user.meetings.count(),
            "ai_command_logs": user.ai_command_logs.count(),
            # CASCADE — removed with the user.
            "work_sessions": user.work_sessions.count(),
            "has_work_policy": hasattr(user, "work_policy"),
            # SET_NULL — detached (authorship history is anonymised, not deleted).
            "created_leads": user.created_leads.count(),
            "assigned_leads": user.assigned_leads.count(),
            "created_clients": user.created_clients.count(),
            "created_projects": user.created_projects.count(),
            "created_tasks": user.created_tasks.count(),
            "created_activities": user.created_activities.count(),
        }

    @classmethod
    def _protect_blockers(cls, impact) -> list:
        blockers = []
        if impact["owned_deals"]:
            blockers.append(f"{impact['owned_deals']} owned deal(s)")
        if impact["owned_meetings"]:
            blockers.append(f"{impact['owned_meetings']} owned meeting(s)")
        if impact["ai_command_logs"]:
            blockers.append(f"{impact['ai_command_logs']} AI command log(s)")
        return blockers

    @action(
        detail=True,
        methods=["get"],
        url_path="delete-impact",
        permission_classes=[IsSuperAdmin],
        throttle_classes=[DangerZoneThrottle],
    )
    def delete_impact(self, request, pk=None):
        user = self.get_object()
        is_self = user.id == request.user.id
        impact = self._ownership_impact(user)
        blockers = self._protect_blockers(impact)
        reason = None
        if is_self:
            reason = "You cannot permanently delete your own account."
        elif blockers:
            reason = (
                "This user still owns protected records that must be reassigned "
                "first: " + ", ".join(blockers) + "."
            )
        return Response(
            {
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "is_active": user.is_active,
                "is_self": is_self,
                "impact": impact,
                "protect_blockers": blockers,
                "deletion_allowed": reason is None,
                "blocked_reason": reason,
                "confirmation_phrase": "DELETE USER",
            }
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="permanent-delete",
        permission_classes=[IsSuperAdmin],
        throttle_classes=[DangerZoneThrottle],
    )
    def permanent_delete(self, request, pk=None):
        target = self.get_object()

        if target.id == request.user.id:
            return danger.error(
                "You cannot permanently delete your own account.", "self_delete", status.HTTP_400_BAD_REQUEST
            )

        guard = (
            danger.check_password(request)
            or danger.check_confirmation(request, "DELETE USER")
            or danger.check_id_matches(request, "user_id", target.id)
        )
        if guard is not None:
            return guard

        with transaction.atomic():
            # Lock both actor and target rows (ascending pk order avoids deadlocks).
            ids = sorted({request.user.id, target.id})
            locked = {u.id: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
            actor = locked.get(request.user.id)
            locked_target = locked.get(target.id)

            # Revalidate the actor is still a superadmin under the lock.
            if actor is None or not is_super_admin(actor):
                return danger.error(
                    "Your superadmin access could not be verified.", "not_superadmin", status.HTTP_403_FORBIDDEN
                )
            if locked_target is None:
                return danger.error("User not found (already deleted).", "not_found", status.HTTP_404_NOT_FOUND)

            # Never leave the CRM with no admin-level user.
            if locked_target.is_admin_role and active_admin_count(exclude_id=locked_target.id) == 0:
                return danger.error(
                    "You cannot delete the last remaining admin.", "last_admin", status.HTTP_409_CONFLICT
                )

            impact = self._ownership_impact(locked_target)
            blockers = self._protect_blockers(impact)
            if blockers:
                return danger.error(
                    "This user still owns protected records that must be reassigned first: "
                    + ", ".join(blockers) + ".",
                    "protected_dependencies",
                    status.HTTP_409_CONFLICT,
                )

            deleted_id = locked_target.id
            deleted_username = locked_target.username
            # Delete. SET_NULL authorship is cleared, CASCADE work sessions/policy
            # and AI confirmations are removed; no PROTECT reference remains.
            locked_target.delete()

            record_event(
                action="user.permanently_deleted",
                category=AuditCategory.USER,
                user=request.user,
                request=request,
                entity_type="User",
                entity_id=deleted_id,
                summary=f"User #{deleted_id} '{deleted_username}' permanently deleted by superadmin.",
                metadata={"impact": impact},
            )

        return Response(
            {
                "detail": "User permanently deleted.",
                "deleted_user_id": deleted_id,
                "impact": impact,
            }
        )
