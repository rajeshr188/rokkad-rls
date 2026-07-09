from __future__ import annotations

import re

from django.db.migrations.operations.base import Operation


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_qualified_name(schema_editor, name: str) -> str:
    parts = name.split(".")
    if not all(parts) or len(parts) > 2:
        raise ValueError(f"Unsupported table name format: {name}")

    for part in parts:
        if not _IDENTIFIER_PATTERN.match(part):
            raise ValueError(f"Unsafe SQL identifier: {part}")

    return ".".join(schema_editor.quote_name(part) for part in parts)


def _policy_name_for_table(table_name: str) -> str:
    sanitized = table_name.replace(".", "_")
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", sanitized)
    return f"tenant_isolation_{sanitized}"


class EnableRLS(Operation):
    reversible = True
    reduces_to_sql = True

    def __init__(
        self,
        *,
        table_name: str,
        workspace_column: str = "workspace_id",
        setting_name: str = "app.current_workspace_id",
        policy_name: str | None = None,
    ):
        self.table_name = table_name
        self.workspace_column = workspace_column
        self.setting_name = setting_name
        self.policy_name = policy_name or _policy_name_for_table(table_name)

    def state_forwards(self, app_label, state):
        return

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return

        table_sql = _quote_qualified_name(schema_editor, self.table_name)
        policy_sql = schema_editor.quote_name(self.policy_name)
        workspace_column_sql = schema_editor.quote_name(self.workspace_column)

        condition = (
            f"{workspace_column_sql} = "
            f"nullif(current_setting('{self.setting_name}', true), '')::uuid"
        )

        schema_editor.execute(f"ALTER TABLE {table_sql} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_sql} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_sql} ON {table_sql};")
        schema_editor.execute(
            f"CREATE POLICY {policy_sql} ON {table_sql} USING ({condition}) WITH CHECK ({condition});"
        )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return

        table_sql = _quote_qualified_name(schema_editor, self.table_name)
        policy_sql = schema_editor.quote_name(self.policy_name)

        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_sql} ON {table_sql};")
        schema_editor.execute(f"ALTER TABLE {table_sql} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_sql} DISABLE ROW LEVEL SECURITY;")

    def describe(self):
        return f"Enable and force RLS on {self.table_name}"

    @property
    def migration_name_fragment(self):
        return "enable_rls"

    def deconstruct(self):
        kwargs = {
            "table_name": self.table_name,
            "workspace_column": self.workspace_column,
            "setting_name": self.setting_name,
        }
        if self.policy_name != _policy_name_for_table(self.table_name):
            kwargs["policy_name"] = self.policy_name
        return (self.__class__.__name__, [], kwargs)
