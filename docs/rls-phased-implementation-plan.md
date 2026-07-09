# RLS Audit and Phased Implementation Plan

Current status: in progress (Phase 1, Phase 2, Phase 3 local/dev, and Phase 5 development scope are completed)
Date: 2026-07-09

Current environment note:

- Project is in development stage only (no production environment yet).
- Phase 3 evidence is tracked for local/dev now; staging/production rows are placeholders until those environments exist.

Development clean-state marker:

- Safe to proceed with new tenant app implementation in development.
- Required local gate remains: `powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1 -IncludeStrictCheck`

## Plan status snapshot

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 1: Baseline enforcement in CI | completed | CI gate with PostgreSQL + strict `check_rls` is active |
| Phase 2: Tenant model normalization | completed | Business tenant models use inheritance contract; only intentional marker-only exception is `common.AuditLog` |
| Phase 3: Database role hardening | completed (local/dev), pending (staging/prod) | Local strict pass achieved; staging/prod blocked only by environment availability |
| Phase 4: Cross-workspace FK safety | in progress (watch mode) | Discovery done and automated trigger guard is now active |
| Phase 5: Runtime context tightening | completed (development scope) | Explicit `transaction.atomic()` service paths now use local context safeguards |

## 1. What is already implemented

Completed foundation work:

- Tenant model contract introduced via TenantModel in [common/models.py](common/models.py#L22)
- Reusable RLS migration operation EnableRLS added in [core/db/migrations/operations.py](core/db/migrations/operations.py#L29)
- Tenant model registry added in [core/db/tenant_registry.py](core/db/tenant_registry.py)
- RLS policy generation command added in [core/management/commands/makerlspolicies.py](core/management/commands/makerlspolicies.py)
- RLS safety verification command added in [core/management/commands/check_rls.py](core/management/commands/check_rls.py)
- Runtime context hardening added in [core/db/rls.py](core/db/rls.py)
- Request-start context clearing added in [core/middleware.py](core/middleware.py#L104)
- Foundation documentation added in [docs/rls-enforcement-foundation.md](docs/rls-enforcement-foundation.md)

Validation completed:

- Django checks pass
- RLS checker passes in local mode with owner-role relaxation
- Strict `check_rls` now passes in local development after role split hardening

## 2. Why phased rollout is recommended

Some controls are safe to enforce immediately in code and CI, while others depend on environment setup or careful data-model migration. A phased rollout avoids production risk while steadily tightening guarantees.

## 3. Phase plan

### Phase 1: Baseline enforcement in CI

Goal: make unsafe tenant schema or policy drift fail quickly.

Actions:

- Add CI job steps to run:
  - manage.py check
  - manage.py makerlspolicies --dry-run
  - manage.py migrate
  - manage.py check_rls
- Keep strict mode for protected environments; allow temporary local override with --allow-owned-tables only for developer machines
- Add a PR checklist section referencing this workflow in [docs/tenant-scoped-models-rls-guide.md](docs/tenant-scoped-models-rls-guide.md)

Status update:

- Completed: CI workflow now includes PostgreSQL service, migrate, `makerlspolicies --dry-run`, and strict `check_rls` gate in [.github/workflows/ci.yml](.github/workflows/ci.yml)
- Added negative-control test proving `check_rls` fails for an unsafe tenant table fixture in [core/tests_rls_foundation.py](core/tests_rls_foundation.py)
- Added positive-control test proving `check_rls` passes for a known safe tenant table in [core/tests_rls_foundation.py](core/tests_rls_foundation.py)

Phase status: completed

Exit criteria:

- Every PR running against PostgreSQL must pass check_rls
- Any missing RLS coverage causes CI failure

### Phase 2: Tenant model normalization

Goal: remove transitional markers and converge all tenant business models on TenantModel inheritance.

Actions:

- Migrate legacy tenant models currently using tenant_rls_required marker to inherit TenantModel or TenantScopedModel
- Keep public/global models explicitly non-tenant
- Re-run makerlspolicies and check_rls during each migration step

Status update:

- Completed: `billing.Subscription`, `memberships.WorkspaceMember`, and `workspace_invitations.WorkspaceInvitation` inherit `TenantModel` directly.
- Transitional marker usage has been reduced to non-business edge cases requiring separate treatment.
- Marker-only concrete model inventory is now intentionally reduced to `common.AuditLog`.
- Added regression guard test to prevent accidental reintroduction of marker-only tenant models in [core/tests_rls_foundation.py](core/tests_rls_foundation.py).
- Policy lock-in: `common.AuditLog` is the only allowed marker-only concrete exception for now; new marker-only models are not permitted.

Phase status: completed

Exit criteria:

- No tenant business model relies only on tenant_rls_required marker
- Tenant model discovery is inheritance-based for all business models
- Any marker-only exception is explicitly documented and guard-tested

### Phase 3: Database role hardening

Goal: ensure runtime role cannot weaken RLS behavior.

Actions:

- Introduce separate migration owner role and runtime app role
- Ensure runtime app role does not own tenant tables
- Ensure runtime app role does not have BYPASSRLS
- Grant runtime role only required DML privileges
- Execute strict check_rls in deploy pipeline with no owner-role override

Status update:

- Operational SQL verification procedures have been documented in [docs/production-deployment-guide.md](docs/production-deployment-guide.md) and [docs/production-operations-runbook.md](docs/production-operations-runbook.md).
- Phase 3 is now implementation-ready with copy/paste checks for runtime role `BYPASSRLS`, table ownership, RLS/FORCE RLS flags, and policy presence.
- Local role split has been completed in development: tenant tables are owned by `rls_rokkad_migration_owner` and app runtime uses `rls_rokkad_user`.
- Local strict `check_rls` now passes with no owner override; relaxed local check remains available for diagnostics.
- Environment execution evidence remains pending for staging and production (not yet created).

Phase status: completed (local/dev), pending (staging/production)

Execution checklist (staging then production):

1. Run role verification SQL from deployment guide under privileged DBA session.
2. Confirm runtime role has `rolbypassrls=false`.
3. Confirm tenant table owners are migration role (not runtime role).
4. Confirm RLS and FORCE RLS are enabled on all tenant tables.
5. Confirm policies exist with both `USING` and `WITH CHECK`.
6. Run strict `python manage.py check_rls` using runtime app credentials.
7. Record results in release notes and attach query output snippets.

Execution evidence log:

| Environment | Date | Strict `check_rls` | Runtime `BYPASSRLS` | Runtime owns tenant tables | Notes |
| --- | --- | --- | --- | --- | --- |
| local | 2026-07-09 | pass | false | no | strict pass verified after ownership transfer to `rls_rokkad_migration_owner` and runtime role `rls_rokkad_user` |
| staging | n/a yet | pending | pending | pending | create staging first, then run Phase 3 SQL verification procedure |
| production | n/a yet | pending | pending | pending | create production first, then run Phase 3 SQL verification procedure |

Step 1-4 execution notes (dev):

1. Step 1 (split roles): completed.
2. Step 2 (migrate as owner): completed in local dev after admin-level ownership transfer.
3. Step 3 (strict check): completed and passing.
4. Step 4 (evidence update): completed in this plan document.

Development-stage next steps (execute now):

1. Keep strict `check_rls` as required local verification (no owner override).
2. Keep `check_rls --allow-owned-tables` available only as a diagnostic fallback.
3. Prepare environment-specific role names in `.env` templates for future staging rollout.
4. Re-run and update evidence after any DB role/ownership change.
5. Promote this checklist to staging immediately when staging environment is created.
6. Use `scripts/run-dev-rls-checks.ps1` as the standard one-command local verification entrypoint.
7. Use `scripts/apply-dev-role-hardening.ps1` only for admin-led remediation if a local role/ownership drift is detected.

Exit criteria:

- Strict check_rls passes in staging and production
- Runtime role ownership findings are zero

Development-stage interim exit criteria:

- Local ownership findings are explicitly tracked and reviewed (not ignored).
- No new tenant model/policy drift is introduced while waiting for staging/production setup.

### Phase 4: Cross-workspace foreign key safety

Goal: prevent semantically invalid cross-tenant references.

Actions:

- Identify high-risk tenant references first (financial and ledger-like domains)
- Add database-level workspace consistency protections for critical pairs:
  - trigger-based checks where composite keys are impractical
  - composite-key patterns where feasible
- Keep service-layer validation as additional guard, not primary guarantee

Status update:

- Initial discovery completed for current tenant business models (`notes`, `memberships`, `billing`, `workspace_invitations`).
- No direct tenant-to-tenant foreign keys were found in current schema, so there are no immediate workspace-consistency trigger candidates to ship now.
- Added automated trigger guard in [core/tests_rls_foundation.py](core/tests_rls_foundation.py) to fail fast if any tenant-to-tenant FK is introduced without explicit Phase 4 review.
- Integrated the trigger guard into the standard local verification flow via [scripts/run-dev-rls-checks.ps1](scripts/run-dev-rls-checks.ps1), so it runs on every dev RLS check pass.
- Current medium-risk semantic relationships to keep on watch:
  - `memberships.WorkspaceMember.user` (global user reference tied to tenant workspace semantics)
  - `workspace_invitations.WorkspaceInvitation.accepted_by` and `invited_by` (global user references in tenant flow)
  - `billing.Subscription.plan` (global plan catalog reference; low risk for cross-workspace, but business-critical)
- Phase 4 implementation trigger: introduce DB-level workspace-consistency checks immediately when first tenant-to-tenant FK appears.

Phase status: in progress (watch mode)

Exit criteria:

- Critical cross-tenant references have DB-enforced workspace consistency
- Negative tests prove cross-workspace linkage attempts fail

### Phase 5: Runtime context tightening

Goal: safely move toward transaction-local context semantics where feasible.

Actions:

- Evaluate request/service transaction boundaries
- Where explicit transaction boundaries are guaranteed, enable RLS_CONTEXT_LOCAL for transaction-local settings
- Keep request-start clear behavior as defense-in-depth against stale session values

Status update:

- Added guard logic in [core/db/rls.py](core/db/rls.py) so LOCAL context is only applied inside explicit `transaction.atomic()` blocks; outside atomic, behavior safely falls back to session scope.
- Updated invitation acceptance flow in [workspace_invitations/services.py](workspace_invitations/services.py) to set workspace context with `local=True` inside its atomic transaction.
- Updated billing webhook subscription-update flow in [billing/services.py](billing/services.py) to propagate `local=True` through its atomic processing path.
- Updated billing webhook atomic boundary in [billing/services.py](billing/services.py) to set workspace context with `local=True` immediately after workspace resolution.
- Updated billing state-transition flow in [billing/services.py](billing/services.py) to set workspace context with `local=True` inside its atomic transaction.
- Added regression tests in [core/tests.py](core/tests.py) to verify local-context fallback outside atomic and local-context activation inside atomic.
- Added webhook regression coverage in [billing/tests.py](billing/tests.py) to verify transaction-local workspace context is requested during webhook processing.
- Added webhook atomic-boundary regression coverage in [billing/tests.py](billing/tests.py) to verify transaction-local workspace context is applied before workspace-scoped webhook operations.
- Added billing transition regression coverage in [billing/tests.py](billing/tests.py) to verify transaction-local workspace context is requested during state transitions.

Phase status: completed (development scope)

Development evidence:

- Explicit `transaction.atomic()` service paths now apply workspace context with `local=True`:
  - [workspace_invitations/services.py](workspace_invitations/services.py)
  - [billing/services.py](billing/services.py)
- Regression suite coverage confirms local-context behavior in middleware and atomic service paths:
  - [core/tests.py](core/tests.py)
  - [billing/tests.py](billing/tests.py)
- Verified repeatedly with local command gates:
  - `python manage.py test billing.tests.BillingWebhookApiTests billing.tests.BillingSubscriptionLifecycleTests core.tests workspace_invitations.tests`
  - `powershell -ExecutionPolicy Bypass -File .\\scripts\\run-dev-rls-checks.ps1 -IncludeStrictCheck`

Exit criteria:

- Context behavior is deterministic under load and pooling
- Regression tests pass for reads, writes, and context reset behavior

## 4. Testing expansion plan

Add or expand tests for:

- cross-workspace read, update, and delete denial
- wrong workspace insert and workspace move update denial
- missing workspace context returns zero tenant rows
- raw SQL and unfiltered ORM remain RLS-protected
- check_rls catches a deliberately unsafe table

Reference existing postgres isolation tests in [memberships/tests_rls_postgres.py](memberships/tests_rls_postgres.py)

## 5. Operational checklist

Before merge:

- makemigrations completed
- makerlspolicies check passes (`python manage.py makerlspolicies --check`)
- migrations applied in PostgreSQL environment
- check_rls passes

Before deploy:

- strict check_rls passes without owner-role override
- role hardening verified
- rollback notes prepared for policy changes

## 6. Decision record

Decision: proceed with phased implementation.

Reason:

- Core foundation is already in place and validated.
- Remaining work includes environment-level hardening and deeper integrity constraints that should be rolled out safely.
