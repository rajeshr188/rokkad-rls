from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import SkipTest
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.apps import apps
from django.db import connection
from django.db import models
from django.test import SimpleTestCase
from django.test import TransactionTestCase

from common.models import TenantModel
from core.db.tenant_registry import TenantModelSpec
from core.db.tenant_registry import iter_tenant_model_specs
from notes.models import Note


class TenantModelNormalizationGuardTests(SimpleTestCase):
    """Guard against accidental reintroduction of marker-only tenant models."""

    def test_only_allowed_concrete_models_use_legacy_tenant_marker(self):
        allowed_labels = {"common.AuditLog"}
        marker_only_labels = {
            model._meta.label
            for model in apps.get_models()
            if not model._meta.abstract
            and getattr(model, "tenant_rls_required", False)
            and not issubclass(model, TenantModel)
        }

        # Keep this list explicit so newly-added marker-only tenant models are reviewed.
        self.assertSetEqual(marker_only_labels, allowed_labels)


class TenantForeignKeySafetyGuardTests(SimpleTestCase):
    """Guard Phase 4 by requiring explicit review of tenant-to-tenant FK edges."""

    def test_no_unreviewed_tenant_to_tenant_foreign_keys(self):
        # Keep explicit and empty until Phase 4 introduces approved DB-level safeguards.
        allowed_edges: set[tuple[str, str, str]] = set()

        tenant_models = {spec.model for spec in iter_tenant_model_specs()}
        discovered_edges: set[tuple[str, str, str]] = set()

        for model in sorted(tenant_models, key=lambda item: item._meta.label):
            for field in model._meta.local_fields:
                if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                    continue

                remote_model = getattr(field.remote_field, "model", None)
                if remote_model not in tenant_models:
                    continue

                discovered_edges.add((
                    model._meta.label,
                    field.name,
                    remote_model._meta.label,
                ))

        self.assertSetEqual(
            discovered_edges,
            allowed_edges,
            msg=(
                "New tenant-to-tenant FK detected. Phase 4 requires explicit DB-level "
                "workspace-consistency safeguards and this allowlist review."
            ),
        )


class CheckRLSCommandNegativeControlTests(TransactionTestCase):
    """Negative-control tests proving check_rls fails for unsafe tenant tables."""

    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def setUp(self):
        self.unsafe_table_name = "core_rls_unsafe_fixture"
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {self.unsafe_table_name} CASCADE")
            cursor.execute(
                f"""
                CREATE TABLE {self.unsafe_table_name} (
                    id BIGSERIAL PRIMARY KEY,
                    workspace_id UUID NOT NULL
                )
                """
            )
            cursor.execute(
                f"CREATE INDEX {self.unsafe_table_name}_workspace_idx ON {self.unsafe_table_name} (workspace_id)"
            )

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {self.unsafe_table_name} CASCADE")

    def test_check_rls_fails_for_table_without_rls_policy(self):
        fake_model = SimpleNamespace(
            _meta=SimpleNamespace(label="core.UnsafeFixture")
        )
        unsafe_spec = TenantModelSpec(
            model=fake_model,
            table_name=self.unsafe_table_name,
            workspace_column="workspace_id",
        )

        with patch(
            "core.management.commands.check_rls.iter_tenant_model_specs",
            return_value=[unsafe_spec],
        ):
            with self.assertRaises(CommandError):
                call_command("check_rls", "--allow-owned-tables")

    def test_check_rls_fails_for_tenant_table_with_unsafe_permissive_policy(self):
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {self.unsafe_table_name} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {self.unsafe_table_name} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"""
                CREATE POLICY {self.unsafe_table_name}_workspace_guard
                ON {self.unsafe_table_name}
                USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
                WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
                """
            )
            cursor.execute(
                f"""
                CREATE POLICY {self.unsafe_table_name}_unsafe_self_read
                ON {self.unsafe_table_name}
                FOR SELECT
                USING (true)
                """
            )

        fake_model = SimpleNamespace(
            _meta=SimpleNamespace(label="core.UnsafeFixture")
        )
        unsafe_spec = TenantModelSpec(
            model=fake_model,
            table_name=self.unsafe_table_name,
            workspace_column="workspace_id",
        )

        with patch(
            "core.management.commands.check_rls.iter_tenant_model_specs",
            return_value=[unsafe_spec],
        ):
            with self.assertRaises(CommandError):
                call_command("check_rls", "--allow-owned-tables")


class CheckRLSCommandPositiveControlTests(TransactionTestCase):
    """Positive-control tests proving check_rls passes for a safe tenant table."""

    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def test_check_rls_passes_for_known_safe_table(self):
        safe_spec = TenantModelSpec(
            model=Note,
            table_name=Note._meta.db_table,
            workspace_column="workspace_id",
        )

        with patch(
            "core.management.commands.check_rls.iter_tenant_model_specs",
            return_value=[safe_spec],
        ):
            call_command("check_rls", "--allow-owned-tables")


class MakeRLSPoliciesCommandCheckModeTests(SimpleTestCase):
    def test_check_mode_fails_when_rls_coverage_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "tenantapp"
            migrations_dir = app_dir / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)

            (migrations_dir / "0001_initial.py").write_text(
                "from django.db import migrations\n\n"
                "class Migration(migrations.Migration):\n"
                "    dependencies = []\n"
                "    operations = []\n",
                encoding="utf-8",
            )

            fake_model = SimpleNamespace(
                _meta=SimpleNamespace(label="tenantapp.TenantThing", app_label="tenantapp")
            )
            fake_spec = TenantModelSpec(
                model=fake_model,
                table_name="tenantapp_tenantthing",
                workspace_column="workspace_id",
            )
            fake_app_config = SimpleNamespace(path=str(app_dir))

            with patch(
                "core.management.commands.makerlspolicies.iter_tenant_model_specs",
                return_value=[fake_spec],
            ), patch(
                "core.management.commands.makerlspolicies.apps.get_app_config",
                return_value=fake_app_config,
            ):
                with self.assertRaises(CommandError):
                    call_command("makerlspolicies", "--check")

    def test_check_mode_passes_when_rls_coverage_exists(self):
        with TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir) / "tenantapp"
            migrations_dir = app_dir / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)

            (migrations_dir / "0001_initial.py").write_text(
                "from django.db import migrations\n\n"
                "class Migration(migrations.Migration):\n"
                "    dependencies = []\n"
                "    operations = []\n",
                encoding="utf-8",
            )
            (migrations_dir / "0002_tenant_rls.py").write_text(
                "from django.db import migrations\n"
                "from core.db.migrations.operations import EnableRLS\n\n"
                "class Migration(migrations.Migration):\n"
                "    dependencies = [(\"tenantapp\", \"0001_initial\")]\n"
                "    operations = [EnableRLS(table_name=\"tenantapp_tenantthing\")]\n",
                encoding="utf-8",
            )

            fake_model = SimpleNamespace(
                _meta=SimpleNamespace(label="tenantapp.TenantThing", app_label="tenantapp")
            )
            fake_spec = TenantModelSpec(
                model=fake_model,
                table_name="tenantapp_tenantthing",
                workspace_column="workspace_id",
            )
            fake_app_config = SimpleNamespace(path=str(app_dir))

            with patch(
                "core.management.commands.makerlspolicies.iter_tenant_model_specs",
                return_value=[fake_spec],
            ), patch(
                "core.management.commands.makerlspolicies.apps.get_app_config",
                return_value=fake_app_config,
            ):
                call_command("makerlspolicies", "--check")
