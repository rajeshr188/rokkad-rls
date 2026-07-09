from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workspace_invitations", "0002_workspace_invitation_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
DROP POLICY IF EXISTS workspace_invitations_workspaceinvitation_workspace_isolation
ON workspace_invitations_workspaceinvitation;
CREATE POLICY workspace_invitations_workspaceinvitation_workspace_isolation
ON workspace_invitations_workspaceinvitation
USING (
    workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid
    OR token = nullif(current_setting('app.current_invitation_token', true), '')
)
WITH CHECK (
    workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid
);
""".strip(),
            reverse_sql="""
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
""".strip(),
        )
    ]
