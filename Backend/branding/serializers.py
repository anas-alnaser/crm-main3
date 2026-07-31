from rest_framework import serializers

from .models import (
    BrandProfile,
    GeneratedDocument,
    GeneratedDocumentSnapshot,
    LegalEntity,
    Signatory,
)


class LegalEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalEntity
        fields = [
            "id", "key", "legal_name", "registration_number", "tax_number", "address",
            "phone", "email", "website", "bank_details", "owner_name", "owner_title",
            "legal_terms", "is_active", "created_at", "updated_at", "last_modified_by",
        ]
        read_only_fields = ["last_modified_by", "created_at", "updated_at"]


class SignatorySerializer(serializers.ModelSerializer):
    signature_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Signatory
        fields = [
            "id", "legal_entity", "name", "title", "signature_image", "signature_image_url",
            "signature_hash", "is_default", "created_at", "updated_at",
        ]
        read_only_fields = ["signature_image", "signature_hash", "created_at", "updated_at"]

    def get_signature_image_url(self, obj):
        return obj.signature_image.url if obj.signature_image else None


class BrandProfileSerializer(serializers.ModelSerializer):
    legal_name = serializers.CharField(source="legal_entity.legal_name", read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = BrandProfile
        fields = [
            "id", "key", "legal_entity", "legal_name", "display_name", "logo", "logo_url", "logo_hash",
            "accent_color", "secondary_color", "website", "public_email", "service_category",
            "document_prefix", "default_signatory", "is_active", "created_at", "updated_at", "last_modified_by",
        ]
        read_only_fields = ["logo", "logo_hash", "last_modified_by", "created_at", "updated_at"]

    def get_logo_url(self, obj):
        return obj.logo.url if obj.logo else None


class GeneratedDocumentSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedDocumentSnapshot
        fields = "__all__"
        read_only_fields = [f.name for f in GeneratedDocumentSnapshot._meta.fields]


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.display_name", read_only=True)
    legal_name = serializers.CharField(source="legal_entity.legal_name", read_only=True)
    snapshot = GeneratedDocumentSnapshotSerializer(read_only=True)
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)

    class Meta:
        model = GeneratedDocument
        fields = [
            "id", "document_type", "document_type_display", "document_number", "brand", "brand_name",
            "legal_entity", "legal_name", "client", "deal", "amount", "currency", "status",
            "template_version", "generated_by", "created_at", "snapshot",
        ]
        read_only_fields = fields
