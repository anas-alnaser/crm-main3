from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_person", "email", "phone", "country", "status", "created_at", "updated_at"]
    list_filter = ["status", "country", "created_at"]
    search_fields = ["name", "contact_person", "email", "phone", "country", "notes"]
