import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
        ("tasks", "0002_task_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="deal",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="sales.deal"),
        ),
    ]
