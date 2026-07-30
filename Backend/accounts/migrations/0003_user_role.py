from django.db import migrations, models


def seed_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.all():
        if user.is_superuser or user.is_staff or user.username == "fueldezign":
            user.role = "admin"
        else:
            user.role = "sales"
        user.save(update_fields=["role"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_alter_user_groups_alter_user_is_active_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(choices=[("admin", "Admin"), ("sales", "Sales")], default="sales", max_length=20),
        ),
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
