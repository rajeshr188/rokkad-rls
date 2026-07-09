from django.db import migrations


def apply_workspace_invitation_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    forward_sql = """
ALTER TABLE workspace_invitations_workspaceinvitation ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_invitations_workspaceinvitation FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_invitations_workspaceinvitation_workspace_isolation
ON workspace_invitations_workspaceinvitation;
CREATE POLICY workspace_invitations_workspaceinvitation_workspace_isolation
ON workspace_invitations_workspaceinvitation
USING (
    workspace_id = current_setting('app.current_workspace_id', true)::uuid
    OR token = current_setting('app.current_invitation_token', true)
)
WITH CHECK (
    workspace_id = current_setting('app.current_workspace_id', true)::uuid
);
""".strip()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(forward_sql)


def revert_workspace_invitation_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    reverse_sql = """
DROP POLICY IF EXISTS workspace_invitations_workspaceinvitation_workspace_isolation
ON workspace_invitations_workspaceinvitation;
ALTER TABLE workspace_invitations_workspaceinvitation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE workspace_invitations_workspaceinvitation DISABLE ROW LEVEL SECURITY;
""".strip()
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(reverse_sql)


class Migration(migrations.Migration):
    dependencies = [
        ("workspace_invitations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_workspace_invitation_rls, revert_workspace_invitation_rls),
    ]
