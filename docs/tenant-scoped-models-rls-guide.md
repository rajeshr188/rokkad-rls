# Tenant-Scoped Models Guide (RLS Safe)

This guide explains how to design tenant-scoped models that obey PostgreSQL RLS and preserve workspace isolation.

## 1. Core Rules

- Every tenant-owned table must include `workspace_id`.
- Every tenant-owned table must have an RLS policy migration.
- Tenant writes should run through services (not ad-hoc view ORM logic).
- Service calls should always include:
  - actor
  - workspace
  - validated payload

## 2. Model Design Pattern

Preferred pattern: inherit from `TenantModel` (or `TenantScopedModel` when `created_by` tracking is needed).

Example:

```python
from django.db import models
from common.models import TenantModel

class Note(TenantModel):
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
```

`TenantModel` provides:

- `id`
- `created_at`, `updated_at`
- `workspace` FK

`TenantScopedModel` extends `TenantModel` and adds:

- `created_by` FK

Rule for new apps:

- tenant business models must inherit `TenantModel`/`TenantScopedModel`
- public/global models must not inherit tenant base classes

Exception policy:

- Do not add new marker-only tenant models (`tenant_rls_required` without `TenantModel` inheritance).
- Current allowed marker-only concrete exception is `common.AuditLog`.

## 3. Migration Pattern For RLS

After creating initial model migration, add RLS migration using `tenant_rls_sql`.

Example:

```python
from django.db import migrations
from core.db.rls import tenant_rls_sql

def apply_model_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    forward_sql, _ = tenant_rls_sql(table_name="notes_note")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(forward_sql)
```

Checklist for every new tenant table:

1. model contains `workspace`
2. RLS migration exists
3. tests include cross-workspace denial assertions

Automation option:

```powershell
.\.venv\Scripts\python.exe manage.py makerlspolicies
```

This command scans registered tenant models and generates missing RLS migrations using the reusable `EnableRLS` operation.

## 4. Service-Layer Pattern

Always use service functions to create/update tenant data.

Service expectations:

- enforce permission checks centrally
- enforce workspace-scoped feature gates
- log sensitive actions (`AuditLog`)

## 5. Query Safety Pattern

- Resolve active workspace from middleware (`request.active_workspace`).
- Ensure DB workspace context is set for PostgreSQL before tenant table access.
- Avoid global queryset access to tenant tables without workspace/actor context.

## 6. Testing Pattern

For tenant model tests:

- Positive: same-workspace read/write succeeds.
- Negative: other-workspace read/write denied.
- Missing-context: no workspace context must not leak data.

Use PostgreSQL-specific integration tests for true RLS behavior.

Recommended CI/deploy gate:

```powershell
.\.venv\Scripts\python.exe manage.py check_rls
```

The command verifies table existence, workspace column/index, RLS+FORCE RLS status, and tenant isolation policy shape (`USING` + `WITH CHECK`).

## 7. Common Mistakes

- Forgetting `workspace_id` on new model.
- Adding model but skipping RLS migration.
- Querying tenant data outside service/middleware context.
- Relying on template/UI hiding without backend checks.
- Introducing new marker-only tenant models instead of inheriting `TenantModel`.

## 8. Review Checklist For PRs

- Does table include `workspace`?
- Is there an RLS migration for the table?
- Are cross-workspace tests included?
- Are writes done through services?
- Are audit logs added for sensitive operations?
- Does `check_rls` pass?

## 9. Standard Workflow For New Tenant Apps

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py makerlspolicies
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check_rls
```

## 10. Role Safety Baseline

- runtime role must not have `BYPASSRLS`
- runtime role should not own tenant tables
- migrations should run with a dedicated migration/owner role

See `docs/rls-enforcement-foundation.md` for the full foundation and phased rollout plan.
