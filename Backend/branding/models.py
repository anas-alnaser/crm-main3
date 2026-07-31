from django.conf import settings
from django.db import models


class DocumentType(models.TextChoices):
    INVOICE = "invoice", "Invoice"
    CONTRACT = "contract", "Contract"
    RECEIPT = "receipt", "Receipt"
    QUOTATION = "quotation", "Quotation"
    PAYMENT_ACK = "payment_acknowledgment", "Payment acknowledgment"


# Short codes used inside generated document numbers.
DOCUMENT_TYPE_CODES = {
    DocumentType.INVOICE: "INV",
    DocumentType.CONTRACT: "CON",
    DocumentType.RECEIPT: "RCT",
    DocumentType.QUOTATION: "QUO",
    DocumentType.PAYMENT_ACK: "PAY",
}


class LegalEntity(models.Model):
    """A legal profile. Fuel has its own; Morph Studio and Morph Solutions share
    a single Morph legal profile (registration, tax, bank, owner, terms)."""

    key = models.SlugField(max_length=40, unique=True)
    legal_name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=120, blank=True)
    tax_number = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=255, blank=True)
    bank_details = models.TextField(blank=True)
    owner_name = models.CharField(max_length=255, blank=True)
    owner_title = models.CharField(max_length=255, blank=True)
    legal_terms = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="modified_legal_entities", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name_plural = "Legal entities"
        ordering = ["legal_name"]

    def __str__(self):
        return self.legal_name


class Signatory(models.Model):
    legal_entity = models.ForeignKey(LegalEntity, related_name="signatories", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True)
    signature_image = models.ImageField(upload_to="signatures/", null=True, blank=True)
    signature_hash = models.CharField(max_length=64, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Signatories"
        ordering = ["legal_entity", "name"]

    def __str__(self):
        return f"{self.name} ({self.legal_entity_id})"


class BrandProfile(models.Model):
    """A presentation brand. Fuel Dezign, Morph Studio, and Morph Solutions are
    three brands; the two Morph brands point at the same shared legal entity but
    keep their own display name, logo, colors, website, and document prefix."""

    key = models.SlugField(max_length=40, unique=True)
    legal_entity = models.ForeignKey(LegalEntity, related_name="brands", on_delete=models.PROTECT)
    display_name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="logos/", null=True, blank=True)
    logo_hash = models.CharField(max_length=64, blank=True)
    accent_color = models.CharField(max_length=16, blank=True)
    secondary_color = models.CharField(max_length=16, blank=True)
    website = models.CharField(max_length=255, blank=True)
    public_email = models.EmailField(blank=True)
    service_category = models.CharField(max_length=120, blank=True)
    document_prefix = models.CharField(max_length=40, help_text="Visible number prefix, e.g. FUEL or MORPH-STUDIO.")
    default_signatory = models.ForeignKey(
        Signatory, related_name="default_for_brands", on_delete=models.SET_NULL, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="modified_brand_profiles", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name


class DocumentSequence(models.Model):
    """Per (legal entity + document type + year) counter. The Morph brands share
    a legal entity, so they share a sequence while showing different prefixes;
    global uniqueness of the final number is guaranteed by
    ``GeneratedDocument.document_number``'s unique constraint."""

    legal_entity = models.ForeignKey(LegalEntity, related_name="sequences", on_delete=models.CASCADE)
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["legal_entity", "document_type", "year"], name="unique_sequence_scope"
            )
        ]

    def __str__(self):
        return f"{self.legal_entity_id}/{self.document_type}/{self.year} = {self.last_number}"


class GeneratedDocument(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    document_number = models.CharField(max_length=64, unique=True)
    brand = models.ForeignKey(BrandProfile, related_name="documents", on_delete=models.PROTECT)
    legal_entity = models.ForeignKey(LegalEntity, related_name="documents", on_delete=models.PROTECT)
    client = models.ForeignKey("clients.Client", related_name="documents", on_delete=models.SET_NULL, null=True, blank=True)
    deal = models.ForeignKey("sales.Deal", related_name="documents", on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="JOD")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    template_version = models.CharField(max_length=20, default="v1")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="generated_documents", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document_type", "-created_at"]),
            models.Index(fields=["brand", "-created_at"]),
        ]

    def __str__(self):
        return self.document_number


class GeneratedDocumentSnapshot(models.Model):
    """Immutable copy of every brand/legal value used at generation time.

    Editing a brand or legal entity later never changes an existing document:
    all display values are frozen here (and mirrored in ``data`` as the full
    JSON snapshot). Historical Fuel documents stay Fuel documents forever."""

    document = models.OneToOneField(GeneratedDocument, related_name="snapshot", on_delete=models.CASCADE)

    presentation_brand_key = models.CharField(max_length=40)
    presentation_brand_name = models.CharField(max_length=255)
    legal_entity_key = models.CharField(max_length=40)
    legal_name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=120, blank=True)
    tax_number = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=255, blank=True)
    website = models.CharField(max_length=255, blank=True)
    bank_details = models.TextField(blank=True)
    accent_color = models.CharField(max_length=16, blank=True)
    document_prefix = models.CharField(max_length=40, blank=True)
    logo_hash = models.CharField(max_length=64, blank=True)
    logo_reference = models.CharField(max_length=255, blank=True)
    signatory_name = models.CharField(max_length=255, blank=True)
    signatory_title = models.CharField(max_length=255, blank=True)
    signature_hash = models.CharField(max_length=64, blank=True)
    signature_reference = models.CharField(max_length=255, blank=True)
    terms = models.TextField(blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    template_version = models.CharField(max_length=20, blank=True)
    generated_by_username = models.CharField(max_length=150, blank=True)
    generated_at = models.DateTimeField()
    # Full frozen snapshot (superset of the columns above) for exact reproduction.
    data = models.JSONField(default=dict)

    def __str__(self):
        return f"Snapshot of {self.document_id}"
