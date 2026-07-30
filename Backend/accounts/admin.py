from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("CRM", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("CRM", {"fields": ("role",)}),)
    list_display = ["username", "email", "role", "is_staff", "is_superuser", "is_active"]
    list_filter = ["role", "is_staff", "is_superuser", "is_active"]
