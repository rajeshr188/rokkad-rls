from django.db import migrations

from core.db.migrations.operations import EnableRLS


class Migration(migrations.Migration):
    dependencies = [
        ("party", "0003_partyaddress_partycodesequence_partycontactmethod_and_more"),
    ]

    operations = [
        EnableRLS(table_name="party_partyaddress", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partycodesequence", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partycontactmethod", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partydocument", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partyidentifier", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partyrelationship", workspace_column="workspace_id"),
        EnableRLS(table_name="party_partyrole", workspace_column="workspace_id"),
    ]
