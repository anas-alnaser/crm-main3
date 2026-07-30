from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=User.Role.choices, read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "is_active", "role"]


class UserManagementSerializer(serializers.ModelSerializer):
    temp_password = serializers.CharField(write_only=True, required=False, min_length=8)
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
