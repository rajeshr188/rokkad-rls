from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("memberships", "0003_workspace_member_self_read_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
DROP POLICY IF EXISTS memberships_workspacemember_self_read ON memberships_workspacemember;
CREATE POLICY memberships_workspacemember_self_read
ON memberships_workspacemember
FOR SELECT
USING (
    workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid
    AND user_id = nullif(current_setting('app.current_actor_id', true), '')::integer
);
""".strip(),
            reverse_sql="""
DROP POLICY IF EXISTS memberships_workspacemember_self_read ON memberships_workspacemember;
CREATE POLICY memberships_workspacemember_self_read
ON memberships_workspacemember
FOR SELECT
USING (user_id = nullif(current_setting('app.current_actor_id', true), '')::integer);
""".strip(),
        )
    ]
