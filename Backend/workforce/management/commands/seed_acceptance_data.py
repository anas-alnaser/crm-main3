"""Create clearly-tagged synthetic data for manual acceptance testing.

Everything created is tagged with the ACCEPTANCE marker so it can be removed
cleanly afterwards. No real phone numbers are used (555-01xx range). Run:

    python manage.py seed_acceptance_data
    python manage.py seed_acceptance_data --cleanup   # remove only tagged data

Safe to run against a local/dev database. Do NOT run against the shared Supabase
project or production.
"""
from datetime import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from leads.models import Lead
from workforce.models import EmployeeWorkPolicy

User = get_user_model()

TAG = "[ACCEPTANCE]"
ADMIN_USERNAME = "acc_admin"
EMPLOYEE_USERNAME = "acc_rep"
DEFAULT_PASSWORD = "acceptance-pass-123"
# Documentation-only phone range; not real numbers.
FAKE_PHONES = ["+96279550101", "+96279550102", "+96279550103"]


class Command(BaseCommand):
    help = "Seed or clean clearly-tagged synthetic acceptance-test data."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup", action="store_true", help="Remove only tagged acceptance data.")

    def handle(self, *args, **options):
        if options["cleanup"]:
            return self._cleanup()
        self._seed()

    @transaction.atomic
    def _seed(self):
        admin, _ = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={"role": "admin", "is_staff": True, "first_name": "Acceptance", "last_name": "Admin", "email": "acc_admin@example.test"},
        )
        admin.set_password(DEFAULT_PASSWORD)
        admin.save()

        rep, _ = User.objects.get_or_create(
            username=EMPLOYEE_USERNAME,
            defaults={"role": "sales", "first_name": "Acceptance", "last_name": "Rep", "email": "acc_rep@example.test"},
        )
        rep.set_password(DEFAULT_PASSWORD)
        rep.save()

        EmployeeWorkPolicy.objects.update_or_create(
            user=rep,
            defaults={
                "shift_tracking_required": True,
                "is_active": True,
                "timezone": "Asia/Amman",
                "earliest_start_time": time(9, 0),
                "latest_end_time": time(21, 0),
                "daily_target_minutes": 180,
                "monthly_target_minutes": 3600,
                "basic_salary": 150,
                "salary_currency": "JOD",
            },
        )

        for i, phone in enumerate(FAKE_PHONES):
            Lead.objects.get_or_create(
                normalized_phone=phone,
                defaults={
                    "name": f"{TAG} Test Lead {i + 1}",
                    "original_phone": phone,
                    "source": "acceptance",
                    "assigned_to": rep,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded acceptance data.\n"
            f"  Admin:    {ADMIN_USERNAME} / {DEFAULT_PASSWORD}\n"
            f"  Employee: {EMPLOYEE_USERNAME} / {DEFAULT_PASSWORD} (shift-required policy, 9AM-9PM Amman)\n"
            f"  Leads:    {len(FAKE_PHONES)} tagged '{TAG}', assigned to {EMPLOYEE_USERNAME}."
        ))

    @transaction.atomic
    def _cleanup(self):
        leads = Lead.objects.filter(name__startswith=TAG)
        lead_count = leads.count()
        leads.delete()
        users = User.objects.filter(username__in=[ADMIN_USERNAME, EMPLOYEE_USERNAME])
        user_count = users.count()
        # Deleting the users cascades their policies and sessions.
        users.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed {lead_count} tagged lead(s) and {user_count} acceptance user(s). Only tagged data was touched."
        ))
