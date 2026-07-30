import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_default_pipeline(apps, schema_editor):
    Pipeline = apps.get_model("sales", "Pipeline")
    Stage = apps.get_model("sales", "Stage")

    pipeline, _ = Pipeline.objects.get_or_create(name="Default Pipeline", defaults={"is_default": True})
    stages = [
        ("Lead", 1, False, False),
        ("Contacted", 2, False, False),
        ("Proposal", 3, False, False),
        ("Negotiation", 4, False, False),
        ("Won", 5, True, False),
        ("Lost", 6, False, True),
    ]
    for name, order, is_won, is_lost in stages:
        Stage.objects.get_or_create(
            pipeline=pipeline,
            name=name,
            defaults={"order": order, "is_won": is_won, "is_lost": is_lost},
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0002_client_updated_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pipeline",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("is_default", models.BooleanField(default=False)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Stage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_won", models.BooleanField(default=False)),
                ("is_lost", models.BooleanField(default=False)),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stages", to="sales.pipeline")),
            ],
            options={"ordering": ["pipeline", "order", "name"], "unique_together": {("pipeline", "name")}},
        ),
        migrations.CreateModel(
            name="Deal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("contact_person", models.CharField(blank=True, max_length=255)),
                ("value", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("currency", models.CharField(default="JOD", max_length=3)),
                ("status", models.CharField(choices=[("open", "Open"), ("won", "Won"), ("lost", "Lost")], default="open", max_length=20)),
                ("expected_close_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deals", to="clients.client")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deals", to=settings.AUTH_USER_MODEL)),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deals", to="sales.pipeline")),
                ("stage", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deals", to="sales.stage")),
            ],
            options={"ordering": ["-updated_at", "-created_at"]},
        ),
        migrations.RunPython(seed_default_pipeline, migrations.RunPython.noop),
    ]
