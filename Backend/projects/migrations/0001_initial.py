import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("clients", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("type", models.CharField(choices=[("branding", "Branding"), ("web", "Web"), ("dev", "Dev"), ("other", "Other")], default="branding", max_length=20)),
                ("status", models.CharField(choices=[("lead", "Lead"), ("proposal", "Proposal"), ("in_progress", "In progress"), ("delivered", "Delivered"), ("paid", "Paid")], default="lead", max_length=20)),
                ("budget", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("deadline", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="projects", to="clients.client")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
