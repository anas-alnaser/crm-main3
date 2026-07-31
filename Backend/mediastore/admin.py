from django.contrib import admin

from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("name", "content_type", "size", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("name", "content_type", "size", "created_at", "updated_at")

    def has_add_permission(self, request):
        # Rows are created only through uploads, never hand-edited.
        return False
