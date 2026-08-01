from django.db.models import Q
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=User.Role.choices, read_only=True)
    # Safe booleans only. The frontend uses is_staff + is_superuser + role to
    # decide whether to render superadmin-only destructive controls; the server
    # re-enforces every such action, so these never grant access on their own.
    # Password hashes, permission internals, and tokens are never exposed.
    is_superuser = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "is_superuser", "is_active", "role"]


class PasswordResetSerializer(serializers.Serializer):
    temp_password = serializers.CharField(write_only=True, min_length=8, max_length=128)


class UserManagementSerializer(serializers.ModelSerializer):
    temp_password = serializers.CharField(write_only=True, required=False, min_length=8, max_length=128)
    role = serializers.ChoiceField(choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "role",
            "temp_password",
        ]
        read_only_fields = ["id"]

    def _email_taken(self, email):
        queryset = User.objects.filter(email__iexact=email)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        return queryset.exists()

    def _would_remove_last_admin(self):
        """True if this update demotes/deactivates the only remaining admin."""
        active_admins = User.objects.filter(is_active=True).filter(
            Q(role=User.Role.ADMIN) | Q(is_superuser=True) | Q(is_staff=True)
        )
        others = active_admins.exclude(pk=self.instance.pk)
        return not others.exists()

    def validate(self, attrs):
        request = self.context["request"]
        if not request.user.is_admin_role:
            raise serializers.ValidationError("Only admins can manage users.")

        if self.instance is None and not attrs.get("temp_password"):
            raise serializers.ValidationError({"temp_password": "Temporary password is required."})
        if self.instance is None and "role" not in attrs:
            raise serializers.ValidationError({"role": "Role is required."})
        if attrs.get("role") == User.Role.ADMIN and not request.user.is_admin_role:
            raise serializers.ValidationError({"role": "Only admins can assign the admin role."})

        email = attrs.get("email")
        if email and self._email_taken(email):
            raise serializers.ValidationError({"email": "A user with this email already exists."})

        # Protect the last remaining admin from being demoted or deactivated.
        if self.instance is not None and self.instance.is_admin_role:
            demoting = attrs.get("role") == User.Role.SALES and self.instance.role == User.Role.ADMIN
            deactivating = attrs.get("is_active") is False and self.instance.is_active
            if (demoting or deactivating) and self._would_remove_last_admin():
                raise serializers.ValidationError("You cannot remove admin access from the last active admin.")

        return attrs

    def create(self, validated_data):
        temp_password = validated_data.pop("temp_password")
        user = User(**validated_data)
        user.set_password(temp_password)
        if user.role == User.Role.ADMIN:
            user.is_staff = True
        else:
            user.is_staff = False
            user.is_superuser = False
        user.save()
        return user

    def update(self, instance, validated_data):
        temp_password = validated_data.pop("temp_password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if "role" in validated_data:
            if instance.role == User.Role.ADMIN:
                instance.is_staff = True
            else:
                instance.is_staff = False
                instance.is_superuser = False
        if temp_password:
            instance.set_password(temp_password)
        instance.save()
        return instance
