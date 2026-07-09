# RLS Enforcement Foundation

This document defines the reusable, fail-closed RLS foundation for tenant-scoped Django apps.

## 1. Scope

This foundation covers tenant data isolation only:

- tenant model contract
- PostgreSQL RLS policy enforcement
- request/runtime DB context handling
- migration automation
- deployment safety checks

It intentionally does not define product/business authorization logic.

## 2. Tenant Model Contract

### Rule

If a model stores tenant business data, it must be tenant-scoped and RLS-protected.

### Standard Base

Use `common.models.TenantModel`:

- required indexed `workspace` foreign key
- `tenant_rls_required = True`

`TenantScopedModel` extends `TenantModel` and adds `created_by`.

### Legacy Compatibility

Legacy models that are tenant-scoped but do not inherit `TenantModel` must set:

```python
tenant_rls_required = True
```

This is transitional; new tenant models should inherit `TenantModel` or `TenantScopedModel`.

Current explicit exception policy:

- The only allowed concrete marker-only model is `common.AuditLog`.
- No new marker-only concrete models may be introduced.
- If a new exception is unavoidable, document the rationale in the phased plan and add/adjust guard coverage in `core.tests_rls_foundation`.

## 3. Runtime RLS Context

Context keys:

- `app.current_workspace_id`
- `app.current_actor_id`
- `app.current_invitation_token`

Helpers are in `core/db/rls.py`.

### Local vs Session Scope

`set_config(..., true)` is transaction-local.

- Safe when the request/service runs in an explicit transaction.
- Under Django autocommit, transaction-local values can disappear too early.

Default in this project is session-level (`RLS_CONTEXT_LOCAL=false`) with explicit request-start clearing in `RLSContextMiddleware`:

- clears all context keys first
- sets actor/workspace for current request

This avoids stale pooled-connection context leakage and keeps fail-closed behavior when workspace is missing.

## 4. Generic Policy Pattern

Use `EnableRLS` migration operation or equivalent SQL:

- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`
- policy with both `USING` and `WITH CHECK`
- null-safe setting cast via `nullif(current_setting(...), '')::uuid`

This makes reads and writes fail closed when context is missing or incorrect.

## 5. Migration Automation

### Custom Operation

`core/db/migrations/operations.py` provides `EnableRLS`.

Features:

- idempotent policy recreation
- reversible
- safe identifier handling
- explicit SQL for security clarity

### Command: `makerlspolicies`

```powershell
.\.venv\Scripts\python.exe manage.py makerlspolicies
```

Behavior:

- scans tenant model registry
- detects tenant tables missing migration-level RLS coverage
- generates app migrations using `EnableRLS`

Recommended workflow:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py makerlspolicies
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check_rls
```

## 6. Deployment Gate: `check_rls`

```powershell
.\.venv\Scripts\python.exe manage.py check_rls
```

Validations per tenant model table:

- table exists
- workspace column exists
- workspace column indexed
- RLS enabled
- FORCE RLS enabled
- policy exists with both `USING` and `WITH CHECK`
- policy tied to `current_setting`

Role safety checks:

- runtime role must not have `BYPASSRLS`
- runtime role should not own tenant tables

Use in CI and deploy gates.

Recommended command gates:

- `python manage.py makerlspolicies --check` (fails if any tenant model lacks RLS migration coverage)
- `python manage.py check_rls` (strict role/policy/table safety validation)

## 7. Database Role Safety

Recommended role split:

- migration/owner role:
  - owns schema/tables
  - runs migrations
- runtime app role:
  - no `BYPASSRLS`
  - not owner of tenant tables
  - only required DML grants

The app cannot fully enforce role provisioning; enforce with infra/IaC and fail deploy via `check_rls`.

## 8. App Creation Rules

Every new tenant app must follow:

1. tenant models inherit `TenantModel` (or `TenantScopedModel`)
2. no user-supplied `workspace_id` in forms/APIs
3. workspace injected from request/service context
4. migrations include RLS policy migration (`EnableRLS`)
5. `check_rls` passes before merge/deploy
6. tests prove cross-workspace isolation

## 9. Foreign Key Workspace Safety

RLS prevents cross-tenant row visibility but does not always prevent semantically invalid cross-workspace references.

For high-risk financial tables, enforce workspace consistency at DB layer:

- prefer composite keys/constraints where feasible
- otherwise add `BEFORE INSERT/UPDATE` trigger checks for workspace consistency

Service validation should remain, but DB-level checks are preferred for critical paths.

## 10. Testing Matrix

Minimum required tests for each tenant app:

- workspace A cannot read workspace B rows
- workspace A cannot update/delete workspace B rows
- wrong workspace insert/update fails
- missing workspace context returns zero rows
- raw SQL without workspace filter remains RLS-protected
- runtime role has no `BYPASSRLS`
- `check_rls` catches unsafe/missing policy coverage

## 11. Safe Rollout Plan

Phase 1:

- adopt `TenantModel` contract for new tenant models
- add `makerlspolicies` and `check_rls` to CI

Phase 2:

- migrate legacy tenant models to `TenantModel` where schema-compatible
- keep marker-only usage limited to explicitly documented exceptions (currently `common.AuditLog`)

Phase 3:

- add DB-level workspace consistency checks on high-risk cross-tenant FK paths
- optionally move to transaction-local context (`RLS_CONTEXT_LOCAL=true`) once request/service transaction boundaries are explicit
