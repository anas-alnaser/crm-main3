from decimal import Decimal

from crm.apitestbase import APITestBase
from branding.models import BrandProfile, DocumentType, GeneratedDocument, LegalEntity
from branding.services import generate_document


class SeedDataTests(APITestBase):
    def test_brands_and_legal_entities_seeded(self):
        # From the data migration.
        self.assertTrue(LegalEntity.objects.filter(key="fuel").exists())
        self.assertTrue(LegalEntity.objects.filter(key="morph").exists())
        self.assertEqual(BrandProfile.objects.filter(key__in=["fuel_dezign", "morph_studio", "morph_solutions"]).count(), 3)

    def test_morph_brands_share_legal_entity(self):
        studio = BrandProfile.objects.get(key="morph_studio")
        solutions = BrandProfile.objects.get(key="morph_solutions")
        self.assertEqual(studio.legal_entity_id, solutions.legal_entity_id)

    def test_fuel_has_own_legal_entity(self):
        fuel = BrandProfile.objects.get(key="fuel_dezign")
        studio = BrandProfile.objects.get(key="morph_studio")
        self.assertNotEqual(fuel.legal_entity_id, studio.legal_entity_id)

    def test_legal_identifiers_not_fabricated(self):
        # The seed must not invent registration/tax/bank details.
        fuel = LegalEntity.objects.get(key="fuel")
        self.assertEqual(fuel.registration_number, "")
        self.assertEqual(fuel.tax_number, "")
        self.assertEqual(fuel.bank_details, "")


class DocumentGenerationTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.fuel = BrandProfile.objects.get(key="fuel_dezign")
        self.studio = BrandProfile.objects.get(key="morph_studio")
        self.solutions = BrandProfile.objects.get(key="morph_solutions")

    def test_generate_creates_document_and_snapshot(self):
        doc = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin, amount=Decimal("100"))
        self.assertTrue(doc.document_number.startswith("FUEL-INV-"))
        self.assertTrue(hasattr(doc, "snapshot"))
        self.assertEqual(doc.snapshot.presentation_brand_key, "fuel_dezign")

    def test_prefixes_differ_per_brand(self):
        d1 = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin)
        d2 = generate_document(brand=self.studio, document_type=DocumentType.INVOICE, user=self.admin)
        d3 = generate_document(brand=self.solutions, document_type=DocumentType.CONTRACT, user=self.admin)
        self.assertTrue(d1.document_number.startswith("FUEL-INV-"))
        self.assertTrue(d2.document_number.startswith("MORPH-STUDIO-INV-"))
        self.assertTrue(d3.document_number.startswith("MORPH-SOLUTIONS-CON-"))

    def test_numbers_are_unique_and_increment(self):
        d1 = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin)
        d2 = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin)
        self.assertNotEqual(d1.document_number, d2.document_number)
        n1 = int(d1.document_number.rsplit("-", 1)[1])
        n2 = int(d2.document_number.rsplit("-", 1)[1])
        self.assertEqual(n2, n1 + 1)

    def test_morph_brands_share_sequence(self):
        # Studio + Solutions share the Morph legal entity, so an invoice sequence
        # is shared (global uniqueness preserved), but prefixes differ.
        d1 = generate_document(brand=self.studio, document_type=DocumentType.INVOICE, user=self.admin)
        d2 = generate_document(brand=self.solutions, document_type=DocumentType.INVOICE, user=self.admin)
        n1 = int(d1.document_number.rsplit("-", 1)[1])
        n2 = int(d2.document_number.rsplit("-", 1)[1])
        self.assertEqual(n2, n1 + 1)

    def test_snapshot_is_immutable_to_brand_edits(self):
        doc = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin)
        original_name = doc.snapshot.presentation_brand_name
        # Change the brand later.
        self.fuel.display_name = "Renamed Brand"
        self.fuel.save()
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot.presentation_brand_name, original_name)
        self.assertNotEqual(doc.snapshot.presentation_brand_name, "Renamed Brand")

    def test_historical_fuel_document_stays_fuel(self):
        doc = generate_document(brand=self.fuel, document_type=DocumentType.INVOICE, user=self.admin)
        self.assertEqual(doc.snapshot.legal_entity_key, "fuel")
        # Reassign the brand to the Morph entity later; the old doc is unaffected.
        morph = LegalEntity.objects.get(key="morph")
        self.fuel.legal_entity = morph
        self.fuel.save()
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot.legal_entity_key, "fuel")


class BrandingAPITests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales(username="rep")

    def test_brands_readable_by_all(self):
        self.auth(self.sales)
        resp = self.client.get("/api/brands/")
        self.assertEqual(resp.status_code, 200)

    def test_only_admin_can_modify_brand(self):
        brand = BrandProfile.objects.get(key="fuel_dezign")
        self.auth(self.sales)
        resp = self.client.patch(f"/api/brands/{brand.id}/", {"accent_color": "#fff"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_legal_entities_admin_only(self):
        self.auth(self.sales)
        self.assertEqual(self.client.get("/api/legal-entities/").status_code, 403)
        self.auth(self.admin)
        self.assertEqual(self.client.get("/api/legal-entities/").status_code, 200)

    def test_generate_via_api(self):
        brand = BrandProfile.objects.get(key="fuel_dezign")
        self.auth(self.admin)
        resp = self.client.post(
            "/api/documents/generate/",
            {"brand": brand.id, "document_type": "invoice", "amount": "250"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["document_number"].startswith("FUEL-INV-"))
        self.assertIsNotNone(resp.data["snapshot"])

    def test_generated_document_number_unique_constraint(self):
        doc = generate_document(brand=BrandProfile.objects.get(key="fuel_dezign"), document_type=DocumentType.INVOICE, user=self.admin)
        with self.assertRaises(Exception):
            GeneratedDocument.objects.create(
                document_type="invoice", document_number=doc.document_number,
                brand=doc.brand, legal_entity=doc.legal_entity,
            )
