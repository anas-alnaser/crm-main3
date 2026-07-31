from django.test import SimpleTestCase

from crm.apitestbase import APITestBase
from crm.dbconfig import DatabaseConfigurationError, build_database_config, redact_database_url
from clients.models import Client


class DatabaseConfigTests(SimpleTestCase):
    def test_redacts_credentials(self):
        redacted = redact_database_url("postgresql://user:secret@db.example.com:5432/appdb")
        self.assertNotIn("secret", redacted)
        self.assertNotIn("user", redacted.split("@")[0].replace("u***", ""))
        self.assertIn("db.example.com", redacted)
        self.assertIn("5432", redacted)
        self.assertIn("appdb", redacted)

    def test_redacts_none(self):
        self.assertEqual(redact_database_url(None), "(not set)")

    def test_database_url_applies_ssl_and_conn_age(self):
        env = {"DATABASE_URL": "postgresql://u:p@h:5432/db", "DATABASE_SSLMODE": "require", "DATABASE_CONN_MAX_AGE": "60"}
        config = build_database_config(lambda k, d=None: env.get(k, d), debug=False)
        self.assertIn("postgresql", config["ENGINE"])
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")
        self.assertEqual(config["CONN_MAX_AGE"], 60)

    def test_production_requires_database(self):
        with self.assertRaises(DatabaseConfigurationError):
            build_database_config(lambda k, d=None: d, debug=False)

    def test_dev_falls_back_to_sqlite(self):
        config = build_database_config(lambda k, d=None: d, debug=True)
        self.assertIn("sqlite3", config["ENGINE"])

    def test_postgres_vars_no_forced_ssl(self):
        env = {"POSTGRES_DB": "crm", "POSTGRES_USER": "crm", "POSTGRES_PASSWORD": "crm", "POSTGRES_HOST": "localhost"}
        config = build_database_config(lambda k, d=None: env.get(k, d), debug=False)
        self.assertIn("postgresql", config["ENGINE"])
        # Local/Docker PostgreSQL must not have SSL forced.
        self.assertNotIn("OPTIONS", config)


class HealthTests(APITestBase):
    def test_health_is_public_and_ok(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
        self.assertTrue(resp.data["database"])


class PaginationTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        for i in range(30):
            Client.objects.create(name=f"Co {i:02d}", created_by=self.admin)

    def test_pagination_metadata(self):
        self.auth(self.admin)
        data = self.client.get("/api/clients/?page_size=10").data
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["results"]), 10)
        self.assertEqual(data["total_pages"], 3)
        self.assertIsNotNone(data["next"])

    def test_second_page(self):
        self.auth(self.admin)
        data = self.client.get("/api/clients/?page_size=10&page=2").data
        self.assertEqual(data["page"], 2)
        self.assertIsNotNone(data["previous"])

    def test_invalid_page_returns_404(self):
        self.auth(self.admin)
        self.assertEqual(self.client.get("/api/clients/?page=999").status_code, 404)

    def test_page_size_is_capped(self):
        self.auth(self.admin)
        data = self.client.get("/api/clients/?page_size=100000").data
        self.assertLessEqual(len(data["results"]), 200)


class GlobalSearchTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.viewer = self.make_sales(username="viewer")
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = Client.objects.create(name="Searchable Corp", created_by=self.owner)
        self.deal = self.make_deal(self.owner, self.company, self.pipeline, self.stages["lead"], title="Searchable Deal", value="4200.00")

    def test_requires_min_length(self):
        self.auth(self.admin)
        data = self.client.get("/api/search/?q=a").data
        self.assertEqual(data["results"]["clients"], [])

    def test_finds_company_and_deal(self):
        self.auth(self.admin)
        data = self.client.get("/api/search/?q=Searchable").data
        self.assertTrue(any(c["name"] == "Searchable Corp" for c in data["results"]["clients"]))
        self.assertTrue(any(d["title"] == "Searchable Deal" for d in data["results"]["deals"]))

    def test_deal_value_masked_for_non_owner(self):
        self.auth(self.viewer)
        data = self.client.get("/api/search/?q=Searchable").data
        deal_row = next(d for d in data["results"]["deals"] if d["title"] == "Searchable Deal")
        self.assertIsNone(deal_row["value"])

    def test_deal_value_visible_to_owner(self):
        self.auth(self.owner)
        data = self.client.get("/api/search/?q=Searchable").data
        deal_row = next(d for d in data["results"]["deals"] if d["title"] == "Searchable Deal")
        self.assertEqual(deal_row["value"], "4200.00")

    def test_archived_company_excluded(self):
        self.company.is_archived = True
        self.company.save(update_fields=["is_archived"])
        self.auth(self.admin)
        data = self.client.get("/api/search/?q=Searchable").data
        self.assertFalse(any(c["name"] == "Searchable Corp" for c in data["results"]["clients"]))

    def test_search_requires_auth(self):
        self.assertEqual(self.client.get("/api/search/?q=Searchable").status_code, 401)
