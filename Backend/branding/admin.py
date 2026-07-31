from django.contrib import admin

from .models import (
    BrandProfile,
    DocumentSequence,
    GeneratedDocument,
    GeneratedDocumentSnapshot,
    LegalEntity,
    Signatory,
)


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ["legal_name", "key", "is_active"]
    search_fields = ["legal_name", "key"]


@admin.register(Signatory)
class SignatoryAdmin(admin.ModelAdmin):
    list_display = ["name", "title", "legal_entity", "is_default"]


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "key", "legal_entity", "document_prefix", "is_active"]
    search_fields = ["display_name", "key"]


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ["legal_entity", "document_type", "year", "last_number"]


class SnapshotInline(admin.StackedInline):
    model = GeneratedDocumentSnapshot
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in GeneratedDocumentSnapshot._meta.fields]


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ["document_number", "document_type", "brand", "amount", "currency", "created_at"]
    list_filter = ["document_type", "brand", "status"]
    search_fields = ["document_number"]
    inlines = [SnapshotInline]
