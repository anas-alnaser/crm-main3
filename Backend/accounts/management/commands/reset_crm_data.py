"""``python manage.py reset_crm_data`` — full CRM reset from the command line.

Reuses the single authoritative service in ``crm.data_reset`` (no duplicated
logic). Prints model names and safe counts only — never secrets, connection
strings, or field values.

Preview (no writes):

    python manage.py reset_crm_data --keep-user-email you@example.com --dry-run

Real reset (irreversible):

    python manage.py reset_crm_data --keep-user-email you@example.com \
        --confirm "DELETE ALL CRM DATA"

Point it at an alternative environment (e.g. Supabase) either by exporting
``DJANGO_ENV_FILE`` before running, or with ``--env-file`` (loaded relative to
Backend/). A real reset refuses to run on a non-PostgreSQL database unless
``--allow-non-postgres`` is given (controlled tests only).
"""
from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from crm.data_reset import ResetError, preview_crm_reset, reset_crm_data

CONFIRMATION_PHRASE = "DELETE ALL CRM DATA"
User = get_user_model()


class Command(BaseCommand):
    help = "Permanently reset all CRM business data and other users, preserving one superadmin."

    def add_arguments(self, parser):
        parser.add_argument("--keep-user-id", type=int, default=None, help="Id of the superadmin to preserve.")
        parser.add_argument("--keep-user-email", type=str, default=None, help="Email of the superadmin to preserve.")
        parser.add_argument("--dry-run", action="store_true", help="Preview counts only; make no changes.")
        parser.add_argument("--confirm", type=str, default="", help=f'Must equal "{CONFIRMATION_PHRASE}" for a real reset.')
        parser.add_argument("--env-file", type=str, default=None, help="Extra env file (relative to Backend/) to load first.")
        parser.add_argument(
            "--allow-non-postgres",
            action="store_true",
            help="Permit a real reset on a non-PostgreSQL database (controlled tests only).",
        )

    def handle(self, *args, **options):
        if options.get("env_file"):
            self._apply_env_file(options["env_file"])

        keep_id = options.get("keep_user_id")
        keep_email = options.get("keep_user_email")
        if bool(keep_id) == bool(keep_email):
            raise CommandError("Provide exactly one of --keep-user-id or --keep-user-email.")

        user = self._resolve_user(keep_id, keep_email)
        self._require_superadmin(user)

        if options.get("dry_run"):
            self._print_preview(user)
            return

        if options.get("confirm") != CONFIRMATION_PHRASE:
            raise CommandError(
                f'Refusing to reset. Pass --confirm "{CONFIRMATION_PHRASE}" for a real reset, or use --dry-run.'
            )

        vendor = connections["default"].vendor
        if vendor != "postgresql" and not options.get("allow_non_postgres"):
            raise CommandError(
                f"Refusing a real reset on a non-PostgreSQL database (vendor={vendor}). "
                "Use --allow-non-postgres only for controlled tests."
            )

        try:
            result = reset_crm_data(preserved_user=user)
        except ResetError as exc:
            raise CommandError(f"Reset failed: {exc.message}")

        self.stdout.write(self.style.SUCCESS("CRM data reset completed. Superadmin preserved."))
        self._print_counts(result["deleted"], total_label="Total rows deleted", total=result["total_deleted"])
        preserved = result["preserved_user"]
        self.stdout.write(f"  Preserved user: id={preserved['id']} username={preserved['username']}")
        self.stdout.write("  Reseeded brands: " + ", ".join(result["reseeded_config"]["brands"]))

    # -- helpers ----------------------------------------------------------
    def _apply_env_file(self, name: str) -> None:
        from crm.dbconfig import build_database_config
        from crm.settings import _load_single_env_file

        path = Path(settings.BASE_DIR) / name
        if not path.exists():
            raise CommandError(f"Env file not found: {name}")
        _load_single_env_file(path)
        connections.databases["default"] = build_database_config(
            lambda key, default=None: os.environ.get(key, default), debug=settings.DEBUG
        )
        connections["default"].close()

    def _resolve_user(self, keep_id, keep_email):
        if keep_id is not None:
            user = User.objects.filter(pk=keep_id).first()
            if user is None:
                raise CommandError(f"No user with id={keep_id}.")
            return user
        user = User.objects.filter(email__iexact=keep_email).first()
        if user is None:
            raise CommandError(f"No user with email={keep_email}.")
        return user

    def _require_superadmin(self, user) -> None:
        ok = user.is_active and user.is_staff and user.is_superuser and getattr(user, "role", None) == "admin"
        if not ok:
            raise CommandError(
                f"User '{user.username}' is not an eligible superadmin "
                "(must be active, staff, superuser, and role=admin)."
            )

    def _print_preview(self, user) -> None:
        preview = preview_crm_reset(preserved_user=user)
        self.stdout.write(self.style.WARNING("DRY RUN — no changes made."))
        self.stdout.write(f"  Preserved user: id={preview['preserved_user']['id']} username={preview['preserved_user']['username']}")
        self._print_counts(preview["counts"], total_label="Total rows that would be deleted", total=preview["total_rows"])
        self.stdout.write("  Preserved brands: " + ", ".join(preview["preserved_config"]["brands"]))

    def _print_counts(self, counts: dict, *, total_label: str, total: int) -> None:
        for label in sorted(counts):
            self.stdout.write(f"    {label:.<32} {counts[label]}")
        self.stdout.write(self.style.NOTICE(f"  {total_label}: {total}"))
