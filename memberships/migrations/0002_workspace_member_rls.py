from django.db import migrations

from core.db.rls import tenant_rls_sql


def apply_workspace_member_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    forward_sql, _ = tenant_rls_sql(table_name="memberships_workspacemember")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(forward_sql)


def revert_workspace_member_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    _, reverse_sql = tenant_rls_sql(table_name="memberships_workspacemember")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(reverse_sql)


class Migration(migrations.Migration):
    dependencies = [
        ("memberships", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_workspace_member_rls, revert_workspace_member_rls),
    ]
