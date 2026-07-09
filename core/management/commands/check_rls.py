from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.db.tenant_registry import iter_tenant_model_specs


class Command(BaseCommand):
    help = "Validate PostgreSQL RLS coverage for all registered tenant models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-owned-tables",
            action="store_true",
            help="Do not fail when current runtime role owns tenant tables.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("check_rls requires a PostgreSQL connection.")

        specs = iter_tenant_model_specs()
        if not specs:
            self.stdout.write(self.style.WARNING("No tenant models registered."))
            return

        failures: list[str] = []
        warnings: list[str] = []

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            role_row = cursor.fetchone()
            if role_row is None:
                failures.append("Could not resolve current PostgreSQL role metadata.")
            else:
                role_name, bypassrls = role_row
                if bypassrls:
                    failures.append(
                        f"Current DB role '{role_name}' has BYPASSRLS; runtime role must not bypass RLS."
                    )

            for spec in specs:
                label = spec.model._meta.label
                table_name = spec.table_name
                workspace_column = spec.workspace_column

                cursor.execute("SELECT to_regclass(%s)", [table_name])
                table_regclass = cursor.fetchone()[0]
                if not table_regclass:
                    failures.append(f"{label}: table '{table_name}' does not exist.")
                    continue

                cursor.execute(
                    """
                    SELECT
                        c.relrowsecurity,
                        c.relforcerowsecurity,
                        pg_get_userbyid(c.relowner)
                    FROM pg_class c
                    WHERE c.oid = %s::regclass
                    """,
                    [table_name],
                )
                row = cursor.fetchone()
                if row is None:
                    failures.append(f"{label}: table metadata unavailable for '{table_name}'.")
                    continue

                relrowsecurity, relforcerowsecurity, table_owner = row
                if not relrowsecurity:
                    failures.append(f"{label}: RLS is not enabled on '{table_name}'.")
                if not relforcerowsecurity:
                    failures.append(f"{label}: FORCE ROW LEVEL SECURITY is not enabled on '{table_name}'.")

                if not options["allow_owned_tables"] and role_row and table_owner == role_row[0]:
                    failures.append(
                        f"{label}: runtime role '{role_row[0]}' owns '{table_name}', which can weaken RLS guarantees."
                    )

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_attribute
                        WHERE attrelid = %s::regclass
                          AND attname = %s
                          AND NOT attisdropped
                    )
                    """,
                    [table_name, workspace_column],
                )
                if not cursor.fetchone()[0]:
                    failures.append(
                        f"{label}: missing workspace column '{workspace_column}' on '{table_name}'."
                    )

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_index i
                        JOIN pg_attribute a
                          ON a.attrelid = i.indrelid
                         AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = %s::regclass
                          AND a.attname = %s
                    )
                    """,
                    [table_name, workspace_column],
                )
                if not cursor.fetchone()[0]:
                    failures.append(
                        f"{label}: workspace column '{workspace_column}' is not indexed on '{table_name}'."
                    )

                cursor.execute(
                    """
                    SELECT policyname, cmd, permissive, qual, with_check
                    FROM pg_policies
                    WHERE schemaname = current_schema()
                      AND tablename = %s
                    """,
                    [table_name],
                )
                policies = cursor.fetchall()
                if not policies:
                    failures.append(f"{label}: no RLS policies found for '{table_name}'.")
                    continue

                tenant_policy_ok = False
                for policy_name, cmd, permissive, qual, with_check in policies:
                    qual_text = (qual or "").lower()
                    with_check_text = (with_check or "").lower()
                    cmd_text = (cmd or "").upper()
                    permissive_text = (permissive or "").upper()

                    qual_has_tenant_scope = (
                        workspace_column.lower() in qual_text
                        and "current_setting" in qual_text
                    )
                    with_check_has_tenant_scope = (
                        workspace_column.lower() in with_check_text
                        and "current_setting" in with_check_text
                    )

                    # PostgreSQL combines permissive policies with OR. Any permissive
                    # policy that is not tenant-scoped can weaken isolation guarantees.
                    if permissive_text == "PERMISSIVE":
                        if cmd_text in {"ALL", "SELECT", "UPDATE", "DELETE"} and not qual_has_tenant_scope:
                            failures.append(
                                f"{label}: permissive policy '{policy_name}' on '{table_name}' has cmd={cmd_text} without tenant-scoped USING clause."
                            )
                        if cmd_text in {"ALL", "INSERT", "UPDATE"} and not with_check_has_tenant_scope:
                            failures.append(
                                f"{label}: permissive policy '{policy_name}' on '{table_name}' has cmd={cmd_text} without tenant-scoped WITH CHECK clause."
                            )

                    if (
                        qual_has_tenant_scope
                        and with_check_has_tenant_scope
                    ):
                        tenant_policy_ok = True

                if not tenant_policy_ok:
                    failures.append(
                        f"{label}: no tenant isolation policy with USING+WITH CHECK tied to current_setting was found on '{table_name}'."
                    )

                cursor.execute(
                    """
                    SELECT
                        has_table_privilege(current_user, %s, 'SELECT'),
                        has_table_privilege(current_user, %s, 'INSERT'),
                        has_table_privilege(current_user, %s, 'UPDATE'),
                        has_table_privilege(current_user, %s, 'DELETE')
                    """,
                    [table_name, table_name, table_name, table_name],
                )
                select_ok, insert_ok, update_ok, delete_ok = cursor.fetchone()
                if not (select_ok and insert_ok and update_ok and delete_ok):
                    warnings.append(
                        f"{label}: runtime role is missing one or more DML privileges on '{table_name}'."
                    )

        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"RLS CHECK FAILED: {failure}"))
            raise CommandError(f"RLS safety check failed with {len(failures)} issue(s).")

        self.stdout.write(
            self.style.SUCCESS(
                f"RLS safety check passed for {len(specs)} tenant model table(s)."
            )
        )
