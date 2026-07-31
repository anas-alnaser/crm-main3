from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.permissions import IsAdminOrReadOnly, IsAdminRole
from audit.models import AuditCategory
from audit.services import record_event
from clients.models import Client
from crm.imaging import validate_image_file
from sales.models import Deal

from .models import BrandProfile, DocumentType, GeneratedDocument, LegalEntity, Signatory
from .serializers import (
    BrandProfileSerializer,
    GeneratedDocumentSerializer,
    LegalEntitySerializer,
    SignatorySerializer,
)
from .services import BrandingError, generate_document


class LegalEntityViewSet(ModelViewSet):
    queryset = LegalEntity.objects.all()
    serializer_class = LegalEntitySerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    search_fields = ["legal_name", "key"]
    ordering_fields = ["legal_name", "created_at"]

    def perform_create(self, serializer):
        entity = serializer.save(last_modified_by=self.request.user)
        self._audit(entity, "branding.legal_entity_created")

    def perform_update(self, serializer):
        entity = serializer.save(last_modified_by=self.request.user)
        self._audit(entity, "branding.legal_entity_updated")

    def _audit(self, entity, action_code):
        record_event(
            action=action_code, category=AuditCategory.BRANDING, user=self.request.user, request=self.request,
            entity_type="LegalEntity", entity_id=entity.pk, summary=f"Legal entity '{entity.legal_name}' saved.",
        )


class SignatoryViewSet(ModelViewSet):
    queryset = Signatory.objects.select_related("legal_entity")
    serializer_class = SignatorySerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["legal_entity", "is_default"]

    @action(detail=True, methods=["post"], url_path="signature")
    def upload_signature(self, request, pk=None):
        signatory = self.get_object()
        upload = request.FILES.get("file")
        safe_name, hexdigest, _dims = validate_image_file(upload)
        signatory.signature_image.save(f"sig_{signatory.pk}_{safe_name}", upload, save=False)
        signatory.signature_hash = hexdigest
        signatory.save(update_fields=["signature_image", "signature_hash", "updated_at"])
        record_event(
            action="branding.signature_uploaded", category=AuditCategory.BRANDING, user=request.user, request=request,
            entity_type="Signatory", entity_id=signatory.pk, summary=f"Signature uploaded for {signatory.name}.",
            metadata={"hash": hexdigest},
        )
        return Response(self.get_serializer(signatory).data)


class BrandProfileViewSet(ModelViewSet):
    queryset = BrandProfile.objects.select_related("legal_entity", "default_signatory")
    serializer_class = BrandProfileSerializer
    # Admins manage brands; all authenticated users may read them (the document
    # brand selector needs the list).
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["is_active", "legal_entity"]
    search_fields = ["display_name", "key", "document_prefix"]
    ordering_fields = ["display_name", "created_at"]

    def perform_create(self, serializer):
        brand = serializer.save(last_modified_by=self.request.user)
        self._audit(brand, "branding.brand_created")

    def perform_update(self, serializer):
        brand = serializer.save(last_modified_by=self.request.user)
        self._audit(brand, "branding.brand_updated")

    def _audit(self, brand, action_code):
        record_event(
            action=action_code, category=AuditCategory.BRANDING, user=self.request.user, request=self.request,
            entity_type="BrandProfile", entity_id=brand.pk, summary=f"Brand '{brand.display_name}' saved.",
        )

    @action(detail=True, methods=["post"], url_path="logo", permission_classes=[IsAuthenticated, IsAdminRole])
    def upload_logo(self, request, pk=None):
        brand = self.get_object()
        upload = request.FILES.get("file")
        safe_name, hexdigest, _dims = validate_image_file(upload)
        brand.logo.save(f"logo_{brand.key}_{safe_name}", upload, save=False)
        brand.logo_hash = hexdigest
        brand.save(update_fields=["logo", "logo_hash", "updated_at"])
        record_event(
            action="branding.logo_uploaded", category=AuditCategory.BRANDING, user=request.user, request=request,
            entity_type="BrandProfile", entity_id=brand.pk, summary=f"Logo uploaded for {brand.display_name}.",
            metadata={"hash": hexdigest},
        )
        return Response(self.get_serializer(brand).data)


class GeneratedDocumentViewSet(ReadOnlyModelViewSet):
    """Read-only registry of generated documents. Generation is a POST to
    ``/generate/``; snapshots are immutable and never editable."""

    queryset = GeneratedDocument.objects.select_related("brand", "legal_entity", "client", "snapshot")
    serializer_class = GeneratedDocumentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["document_type", "brand", "legal_entity", "status", "client"]
    search_fields = ["document_number"]
    ordering_fields = ["created_at", "document_number"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Non-admins only see documents they generated.
        if not self.request.user.is_admin_role:
            queryset = queryset.filter(generated_by=self.request.user)
        return queryset

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        data = request.data
        brand = BrandProfile.objects.filter(pk=data.get("brand")).first() or \
            BrandProfile.objects.filter(key=data.get("brand")).first()
        if brand is None:
            return Response({"detail": "Brand not found.", "code": "brand_not_found"}, status=status.HTTP_400_BAD_REQUEST)
        document_type = data.get("document_type")
        if document_type not in DocumentType.values:
            return Response({"detail": "Invalid document type.", "code": "bad_type"}, status=status.HTTP_400_BAD_REQUEST)
        client = Client.objects.filter(pk=data.get("client")).first() if data.get("client") else None
        deal = Deal.objects.filter(pk=data.get("deal")).first() if data.get("deal") else None
        try:
            document = generate_document(
                brand=brand,
                document_type=document_type,
                user=request.user,
                client=client,
                deal=deal,
                amount=data.get("amount") or None,
                currency=data.get("currency", "JOD"),
                terms=data.get("terms", ""),
                request=request,
            )
        except BrandingError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)
