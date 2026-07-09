from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from django.apps import apps
from django.core.management.base import CommandError
from django.core.management.base import BaseCommand

from core.db.tenant_registry import iter_tenant_model_specs


class Command(BaseCommand):
    help = "Generate RLS policy migrations for tenant models lacking migration coverage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned migration files without writing them.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fail if any tenant table is missing RLS migration coverage.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        check_mode = options["check"]

        specs_by_app = defaultdict(list)
        for spec in iter_tenant_model_specs():
            specs_by_app[spec.model._meta.app_label].append(spec)

        created_files: list[Path] = []
        missing_coverage_labels: list[str] = []

        for app_label, specs in sorted(specs_by_app.items()):
            app_config = apps.get_app_config(app_label)
            migrations_dir = Path(app_config.path) / "migrations"
            migrations_dir.mkdir(parents=True, exist_ok=True)

            migration_files = sorted(
                p
                for p in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.py")
                if p.is_file()
            )

            covered_tables = self._find_covered_tables(migration_files)
            missing_specs = [spec for spec in specs if spec.table_name not in covered_tables]
            if not missing_specs:
                continue

            missing_coverage_labels.extend(
                f"{spec.model._meta.label} ({spec.table_name})" for spec in missing_specs
            )

            if migration_files:
                latest_migration = migration_files[-1].stem
                next_prefix = int(migration_files[-1].name.split("_", 1)[0]) + 1
            else:
                latest_migration = "0001_initial"
                next_prefix = 1

            migration_name = f"{next_prefix:04d}_auto_rls_policies"
            migration_path = migrations_dir / f"{migration_name}.py"

            content = self._render_migration(
                app_label=app_label,
                dependency=latest_migration,
                missing_specs=missing_specs,
            )

            if check_mode or dry_run:
                self.stdout.write(f"[dry-run] Would create {migration_path}")
            else:
                migration_path.write_text(content, encoding="utf-8")
                created_files.append(migration_path)
                self.stdout.write(self.style.SUCCESS(f"Created {migration_path}"))

        if check_mode:
            if missing_coverage_labels:
                details = "\n".join(f"- {label}" for label in sorted(missing_coverage_labels))
                raise CommandError(
                    "RLS migration coverage is missing for one or more tenant models:\n"
                    f"{details}\n"
                    "Run 'python manage.py makerlspolicies' and commit the generated migration(s)."
                )
            self.stdout.write("RLS migration coverage check passed.")
            return

        if dry_run and not created_files:
            self.stdout.write("Dry run complete.")
        elif not dry_run and not created_files:
            self.stdout.write("All tenant model tables already appear to have RLS migration coverage.")

    @staticmethod
    def _find_covered_tables(migration_files: list[Path]) -> set[str]:
        covered_tables: set[str] = set()
        markers = (
            "EnableRLS(",
            "tenant_rls_sql(",
            "ENABLE ROW LEVEL SECURITY",
        )
        table_name_pattern = re.compile(r"table_name\s*=\s*['\"]([A-Za-z0-9_.]+)['\"]")
        alter_table_pattern = re.compile(
            r"ALTER\s+TABLE\s+([A-Za-z0-9_.\"]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            flags=re.IGNORECASE,
        )

        for path in migration_files:
            text = path.read_text(encoding="utf-8")
            if not any(marker in text for marker in markers):
                continue

            for match in table_name_pattern.finditer(text):
                covered_tables.add(match.group(1))

            for match in alter_table_pattern.finditer(text):
                covered_tables.add(match.group(1).replace('"', ""))

        return covered_tables

    @staticmethod
    def _render_migration(*, app_label: str, dependency: str, missing_specs) -> str:
        operation_lines = []
        for spec in missing_specs:
            operation_lines.append(
                f"        EnableRLS(table_name=\"{spec.table_name}\", workspace_column=\"{spec.workspace_column}\"),"
            )

        operations_block = "\n".join(operation_lines)

        return f"""from django.db import migrations

from core.db.migrations.operations import EnableRLS


class Migration(migrations.Migration):
    dependencies = [
        (\"{app_label}\", \"{dependency}\"),
    ]

    operations = [
{operations_block}
    ]
"""
