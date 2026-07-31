"""Close work sessions whose inactivity or 9:00 PM cap has passed.

Run roughly once per minute in production (cron, a lightweight scheduler
container, or a systemd timer — no Redis/Celery required). The command is
idempotent, transaction-safe, and concurrency-safe: running it twice, or
alongside live request-time reconciliation, never double-credits or double-closes
a session.

    python manage.py close_stale_work_sessions
"""
from django.core.management.base import BaseCommand

from workforce.services import close_stale_sessions


class Command(BaseCommand):
    help = "Close work sessions past their inactivity timeout or 9:00 PM window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print output when a session is actually closed.",
        )

    def handle(self, *args, **options):
        result = close_stale_sessions()
        if not options["quiet"] or result["closed"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reconciled work sessions: inspected {result['inspected']}, closed {result['closed']}."
                )
            )
