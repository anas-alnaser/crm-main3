from django.db import migrations


def backfill_closed_at(apps, schema_editor):
    """Best-effort backfill for deals closed before closed_at existed.

    We use updated_at as the closing timestamp for already won/lost deals.
    This is an approximation for historical records; new transitions set an
    accurate closed_at going forward.
    """
    Deal = apps.get_model("sales", "Deal")
    for deal in Deal.objects.filter(status__in=["won", "lost"], closed_at__isnull=True):
        Deal.objects.filter(pk=deal.pk).update(closed_at=deal.updated_at)


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0003_deal_closed_at"),
    ]

    operations = [
        migrations.RunPython(backfill_closed_at, migrations.RunPython.noop),
    ]
