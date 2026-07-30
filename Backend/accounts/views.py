from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.views import TokenObtainPairView

from crm.throttling import LoginRateThrottle
from .permissions import IsAdminRole
from .models import User
from .serializers import (
    PasswordResetSerializer,
    UserManagementSerializer,
    UserSerializer,
)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login endpoint with IP-based throttling to slow brute-force attempts."""

    throttle_classes = [LoginRateThrottle]


class CurrentUserView(RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


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
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["patch"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
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
