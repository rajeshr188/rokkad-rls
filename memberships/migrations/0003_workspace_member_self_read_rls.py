from django.db import migrations


def apply_workspace_member_self_read_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
ALTER TABLE memberships_workspacemember ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships_workspacemember FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS memberships_workspacemember_workspace_isolation ON memberships_workspacemember;
CREATE POLICY memberships_workspacemember_workspace_isolation
ON memberships_workspacemember
USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);

DROP POLICY IF EXISTS memberships_workspacemember_self_read ON memberships_workspacemember;
CREATE POLICY memberships_workspacemember_self_read
ON memberships_workspacemember
FOR SELECT
USING (user_id = nullif(current_setting('app.current_actor_id', true), '')::integer);
            """.strip()
        )


def revert_workspace_member_self_read_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
DROP POLICY IF EXISTS memberships_workspacemember_self_read ON memberships_workspacemember;
DROP POLICY IF EXISTS memberships_workspacemember_workspace_isolation ON memberships_workspacemember;
CREATE POLICY memberships_workspacemember_workspace_isolation
ON memberships_workspacemember
USING (workspace_id = current_setting('app.current_workspace_id', true)::uuid)
WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::uuid);
            """.strip()
        )


class Migration(migrations.Migration):
    dependencies = [
        ("memberships", "0002_workspace_member_rls"),
    ]

    operations = [
        migrations.RunPython(apply_workspace_member_self_read_rls, revert_workspace_member_self_read_rls),
    ]
