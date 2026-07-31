"""Tests for database-backed media storage.

Confirms that uploaded assets (brand logos, signatures) persist in the database
and are served from it — never off Cloud Run's ephemeral filesystem.
"""
from django.core.files.base import ContentFile
from django.http import Http404
from django.test import RequestFactory, TestCase

from crm.storage import DatabaseStorage
from crm.views import serve_stored_media
from mediastore.models import StoredFile


class DatabaseStorageTests(TestCase):
    def setUp(self):
        self.storage = DatabaseStorage()

    def test_save_persists_bytes_to_database(self):
        name = self.storage.save("logos/logo_test.png", ContentFile(b"PNGBYTES"))
        self.assertEqual(name, "logos/logo_test.png")
        row = StoredFile.objects.get(name=name)
        self.assertEqual(bytes(row.content), b"PNGBYTES")
        self.assertEqual(row.size, len(b"PNGBYTES"))

    def test_roundtrip_open_exists_size_url(self):
        name = self.storage.save("signatures/sig.png", ContentFile(b"SIGDATA"))
        self.assertTrue(self.storage.exists(name))
        self.assertEqual(self.storage.size(name), len(b"SIGDATA"))
        self.assertEqual(self.storage.open(name).read(), b"SIGDATA")
        self.assertEqual(self.storage.url(name), "/media/signatures/sig.png")

    def test_overwrite_same_name_updates_in_place(self):
        self.storage.save("logos/x.png", ContentFile(b"one"))
        self.storage.save("logos/x.png", ContentFile(b"two"))
        rows = StoredFile.objects.filter(name="logos/x.png")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(bytes(rows.first().content), b"two")

    def test_delete(self):
        name = self.storage.save("logos/gone.png", ContentFile(b"data"))
        self.storage.delete(name)
        self.assertFalse(StoredFile.objects.filter(name=name).exists())

    def test_serve_view_returns_bytes_from_database(self):
        self.storage.save("logos/serve.png", ContentFile(b"IMG"))
        StoredFile.objects.filter(name="logos/serve.png").update(content_type="image/png")
        request = RequestFactory().get("/media/logos/serve.png")
        response = serve_stored_media(request, "logos/serve.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response.content, b"IMG")

    def test_serve_view_missing_asset_returns_404(self):
        request = RequestFactory().get("/media/logos/missing.png")
        with self.assertRaises(Http404):
            serve_stored_media(request, "logos/missing.png")
