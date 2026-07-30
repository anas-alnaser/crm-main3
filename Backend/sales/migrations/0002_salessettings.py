from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def create_default_settings(apps, schema_editor):
    SalesSettings = apps.get_model("sales", "SalesSettings")
    SalesSettings.objects.get_or_create(pk=1, defaults={"commission_rate_percent": Decimal("12.00")})


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "commission_rate_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=12,
                        max_digits=5,
                        validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)],
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sales settings",
                "verbose_name_plural": "Sales settings",
            },
        ),
        migrations.RunPython(create_default_settings, migrations.RunPython.noop),
    ]
