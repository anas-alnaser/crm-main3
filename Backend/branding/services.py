"""Document numbering and brand-aware document generation with immutable
snapshots."""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.models import AuditCategory
from audit.services import record_event
from workforce.timezones import business_now

from .models import (
    DOCUMENT_TYPE_CODES,
    BrandProfile,
    DocumentSequence,
    GeneratedDocument,
    GeneratedDocumentSnapshot,
)


class BrandingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _reserve_number(brand: BrandProfile, document_type: str, year: int) -> str:
    """Atomically reserve the next number for the brand's legal-entity sequence.

    The two Morph brands share one legal entity and therefore one sequence, but
    render different visible prefixes. Called inside a transaction; the row is
    locked with ``select_for_update`` so concurrent generations never collide.
    """
    # Ensure the row exists (unique constraint prevents duplicates on races).
    try:
        DocumentSequence.objects.get_or_create(
            legal_entity=brand.legal_entity, document_type=document_type, year=year,
            defaults={"last_number": 0},
        )
    except IntegrityError:  # pragma: no cover - concurrent creation
        pass
    sequence = (
        DocumentSequence.objects.select_for_update()
        .get(legal_entity=brand.legal_entity, document_type=document_type, year=year)
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    code = DOCUMENT_TYPE_CODES.get(document_type, "DOC")
    return f"{brand.document_prefix}-{code}-{year}-{sequence.last_number:04d}"


def build_snapshot_data(brand: BrandProfile, *, signatory=None, terms="", client=None, user=None) -> dict:
    legal = brand.legal_entity
    signatory = signatory or brand.default_signatory
    return {
        "presentation_brand_key": brand.key,
        "presentation_brand_name": brand.display_name,
        "legal_entity_key": legal.key,
        "legal_name": legal.legal_name,
        "registration_number": legal.registration_number,
        "tax_number": legal.tax_number,
        "address": legal.address,
        "phone": legal.phone,
        "email": brand.public_email or legal.email,
        "website": brand.website or legal.website,
        "bank_details": legal.bank_details,
        "accent_color": brand.accent_color,
        "secondary_color": brand.secondary_color,
        "document_prefix": brand.document_prefix,
        "logo_reference": brand.logo.name if brand.logo else "",
        "logo_hash": brand.logo_hash,
        "signatory_name": signatory.name if signatory else legal.owner_name,
        "signatory_title": signatory.title if signatory else legal.owner_title,
        "signature_hash": signatory.signature_hash if signatory else "",
        "signature_reference": signatory.signature_image.name if (signatory and signatory.signature_image) else "",
        "terms": terms or legal.legal_terms,
        "client_name": client.name if client else "",
        "owner_name": legal.owner_name,
        "owner_title": legal.owner_title,
    }


@transaction.atomic
def generate_document(
    *,
    brand: BrandProfile,
    document_type: str,
    user,
    client=None,
    deal=None,
    amount=None,
    currency="JOD",
    terms="",
    signatory=None,
    template_version="v1",
    request=None,
) -> GeneratedDocument:
    if document_type not in DOCUMENT_TYPE_CODES:
        raise BrandingError("bad_type", f"Unsupported document type: {document_type}.")
    if not brand.is_active:
        raise BrandingError("inactive_brand", "This brand profile is inactive.")

    year = business_now().year
    number = _reserve_number(brand, document_type, year)

    document = GeneratedDocument.objects.create(
        document_type=document_type,
        document_number=number,
        brand=brand,
        legal_entity=brand.legal_entity,
        client=client,
        deal=deal,
        amount=amount,
        currency=currency or "JOD",
        template_version=template_version,
        generated_by=user if getattr(user, "is_authenticated", False) else None,
    )

    snapshot_data = build_snapshot_data(brand, signatory=signatory, terms=terms, client=client, user=user)
    snapshot_data.update(
        {
            "document_number": number,
            "document_type": document_type,
            "amount": str(amount) if amount is not None else None,
            "currency": currency or "JOD",
            "generated_by_username": getattr(user, "username", "") or "",
            "generated_at": timezone.now().isoformat(),
            "template_version": template_version,
        }
    )

    GeneratedDocumentSnapshot.objects.create(
        document=document,
        presentation_brand_key=snapshot_data["presentation_brand_key"],
        presentation_brand_name=snapshot_data["presentation_brand_name"],
        legal_entity_key=snapshot_data["legal_entity_key"],
        legal_name=snapshot_data["legal_name"],
        registration_number=snapshot_data["registration_number"],
        tax_number=snapshot_data["tax_number"],
        address=snapshot_data["address"],
        phone=snapshot_data["phone"],
        email=snapshot_data["email"],
        website=snapshot_data["website"],
        bank_details=snapshot_data["bank_details"],
        accent_color=snapshot_data["accent_color"],
        document_prefix=snapshot_data["document_prefix"],
        logo_hash=snapshot_data["logo_hash"],
        logo_reference=snapshot_data["logo_reference"],
        signatory_name=snapshot_data["signatory_name"],
        signatory_title=snapshot_data["signatory_title"],
        signature_hash=snapshot_data["signature_hash"],
        signature_reference=snapshot_data["signature_reference"],
        terms=snapshot_data["terms"],
        client_name=snapshot_data["client_name"],
        template_version=template_version,
        generated_by_username=snapshot_data["generated_by_username"],
        generated_at=timezone.now(),
        data=snapshot_data,
    )

    record_event(
        action="document.generated",
        category=AuditCategory.DOCUMENT,
        user=user,
        request=request,
        entity_type="GeneratedDocument",
        entity_id=document.pk,
        summary=f"{document.get_document_type_display()} {number} generated for brand {brand.display_name}.",
        metadata={"brand": brand.key, "legal_entity": brand.legal_entity.key, "document_number": number},
    )
    record_event(
        action="document.brand_selected",
        category=AuditCategory.DOCUMENT,
        user=user,
        request=request,
        entity_type="BrandProfile",
        entity_id=brand.pk,
        summary=f"Issuing brand selected: {brand.display_name}.",
    )
    return document
