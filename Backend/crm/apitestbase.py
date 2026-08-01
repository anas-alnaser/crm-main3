"""Shared helpers for the API test suites.

Named so it is NOT picked up by Django's ``test*.py`` discovery.
"""
from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts.models import User
from clients.models import Client
from sales.models import Deal, Pipeline, Stage


class APITestBase(APITestCase):
    def setUp(self):
        super().setUp()
        # DRF throttling stores counters in the cache; reset between tests so
        # unrelated tests never trip each other's rate limits.
        cache.clear()

    # -- user factories --------------------------------------------------
    @staticmethod
    def make_admin(username="admin", **kwargs):
        return User.objects.create_user(
            username=username,
            password=kwargs.pop("password", "adminpass123"),
            role=User.Role.ADMIN,
            is_staff=True,
            **kwargs,
        )

    @staticmethod
    def make_superadmin(username="superadmin", **kwargs):
        """A full superadmin: active + staff + Django superuser + role=admin.

        This is the only account permitted to use the permanent-delete and
        full-reset endpoints (see accounts.permissions.is_super_admin)."""
        return User.objects.create_user(
            username=username,
            password=kwargs.pop("password", "superpass123"),
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
            **kwargs,
        )

    @staticmethod
    def make_sales(username="sales", **kwargs):
        return User.objects.create_user(
            username=username,
            password=kwargs.pop("password", "salespass123"),
            role=User.Role.SALES,
            **kwargs,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)
        return user

    # -- sales fixtures ---------------------------------------------------
    @staticmethod
    def make_pipeline_with_stages():
        pipeline = Pipeline.objects.create(name="Sales", is_default=True)
        stages = {
            "lead": Stage.objects.create(pipeline=pipeline, name="Lead", order=1),
            "negotiation": Stage.objects.create(pipeline=pipeline, name="Negotiation", order=2),
            "won": Stage.objects.create(pipeline=pipeline, name="Won", order=3, is_won=True),
            "lost": Stage.objects.create(pipeline=pipeline, name="Lost", order=4, is_lost=True),
        }
        return pipeline, stages

    @staticmethod
    def make_deal(owner, company, pipeline, stage, **kwargs):
        return Deal.objects.create(
            title=kwargs.pop("title", "Test deal"),
            company=company,
            pipeline=pipeline,
            stage=stage,
            owner=owner,
            value=kwargs.pop("value", "1000.00"),
            **kwargs,
        )

    @staticmethod
    def make_company(name="Acme", **kwargs):
        return Client.objects.create(name=name, **kwargs)
