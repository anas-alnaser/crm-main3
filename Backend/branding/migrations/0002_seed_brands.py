"""Seed the brand/legal *structure* only.

This creates the two legal profiles (Fuel, shared Morph) and three presentation
brands (Fuel Dezign, Morph Studio, Morph Solutions) with their known display
names, document prefixes, and shared-legal-entity relationships.

It deliberately does NOT fabricate legal identifiers: registration number, tax
number, bank details, owner name/title, signatures, and legal terms are left
blank for an administrator to complete on the Brand Profiles screen. The
provisional ``legal_name`` mirrors the brand and must be replaced with the real
registered name before issuing documents.
"""
from django.db import migrations


def seed(apps, schema_editor):
    LegalEntity = apps.get_model("branding", "LegalEntity")
    BrandProfile = apps.get_model("branding", "BrandProfile")

    fuel_entity, _ = LegalEntity.objects.get_or_create(
        key="fuel",
        defaults={"legal_name": "Fuel Dezign", "is_active": True},
    )
    morph_entity, _ = LegalEntity.objects.get_or_create(
        key="morph",
        defaults={"legal_name": "Morph", "is_active": True},
    )

    brands = [
        {"key": "fuel_dezign", "entity": fuel_entity, "display_name": "Fuel Dezign", "prefix": "FUEL"},
        {"key": "morph_studio", "entity": morph_entity, "display_name": "Morph Studio", "prefix": "MORPH-STUDIO"},
        {"key": "morph_solutions", "entity": morph_entity, "display_name": "Morph Solutions", "prefix": "MORPH-SOLUTIONS"},
    ]
    for brand in brands:
        BrandProfile.objects.get_or_create(
            key=brand["key"],
            defaults={
                "legal_entity": brand["entity"],
                "display_name": brand["display_name"],
                "document_prefix": brand["prefix"],
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    BrandProfile = apps.get_model("branding", "BrandProfile")
    LegalEntity = apps.get_model("branding", "LegalEntity")
    BrandProfile.objects.filter(key__in=["fuel_dezign", "morph_studio", "morph_solutions"]).delete()
    LegalEntity.objects.filter(key__in=["fuel", "morph"]).delete()


class Migration(migrations.Migration):
    dependencies = [("branding", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
