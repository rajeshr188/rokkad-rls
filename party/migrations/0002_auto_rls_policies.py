from django.db import migrations

from core.db.migrations.operations import EnableRLS


class Migration(migrations.Migration):
    dependencies = [
        ("party", "0001_initial"),
    ]

    operations = [
        EnableRLS(table_name="party_party", workspace_column="workspace_id"),
    ]
