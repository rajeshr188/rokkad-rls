# RLS Multitenancy Guide

This project uses shared-schema multitenancy enforced by PostgreSQL Row Level Security (RLS).

## Purpose

Explain how tenant isolation is enforced end-to-end with PostgreSQL RLS in this codebase.

## Prerequisites

- Familiarity with workspace-based tenancy in this project.
- Basic understanding of PostgreSQL RLS concepts.
- Read access to [rls-enforcement-foundation.md](rls-enforcement-foundation.md).

## Workflow

Follow this order to understand runtime isolation behavior:

1. Multitenancy architecture.
2. Policy context settings.
3. Request/runtime flow.
4. Standard tenant policy and membership exception.

## Multitenancy Architecture

- Single database schema shared by all workspaces.
- Tenant isolation is enforced in database policies, not only app code.
- App sets request/session context that RLS policies consume.

## Context Settings Used By Policies

Primary workspace setting:

- `app.current_workspace_id`

Additional context settings used by specific flows:

- `app.current_actor_id` for actor-scoped membership reads
- `app.current_invitation_token` for invitation acceptance policy

These are written through helpers in `core/db/rls.py`.

## Request Flow

1. Workspace middleware resolves `request.active_workspace` from route slug.
2. RLS middleware sets actor and workspace DB context for PostgreSQL.
3. Tenant queries execute under active RLS policies.
4. PostgreSQL returns only rows allowed by policy predicates.

## Standard Tenant Policy

Most tenant tables use helper-generated policy from `tenant_rls_sql`:

- `USING`: row visible only when `workspace_id == current_setting('app.current_workspace_id')`
- `WITH CHECK`: insert/update allowed only for active workspace id

The implementation uses `nullif(current_setting(...), '')::uuid` to avoid empty-setting cast failures.

## Membership Exception (Actor-Scoped Read)

To support global workspace listing for active memberships, memberships have an additional SELECT policy keyed by:

- `app.current_actor_id`
- `user_id`

This allows reading only the actor's own memberships while preserving tenant isolation.

## Why This Enforces Isolation

Even if application code has a bug in queryset filters, PostgreSQL still enforces policy predicates before returning rows.

Defense in depth:

- app-level permission checks
- middleware context resolution
- database-level RLS policies

## Validation

- Run PostgreSQL integration tests (for example `memberships/tests_rls_postgres.py`).
- Verify each tenant table has RLS migration.
- Test unknown/incorrect context returns zero rows.

## Troubleshooting

### `invalid input syntax for type uuid: ""`

Cause: empty workspace setting cast to UUID.

Resolution: ensure policy uses null-safe cast pattern:

```sql
nullif(current_setting('app.current_workspace_id', true), '')::uuid
```

### Data not visible when expected

- Confirm middleware set `request.active_workspace`.
- Confirm DB vendor is PostgreSQL for RLS behavior.
- Confirm workspace/actor context settings are written before query.

## Operational Notes

- RLS does not replace business authorization; keep central policy checks.
- New tenant tables must not be merged without RLS migration and isolation tests.

## Related Guides

- [tenant-scoped-models-rls-guide.md](tenant-scoped-models-rls-guide.md)
- [rls-enforcement-foundation.md](rls-enforcement-foundation.md)
- [rls-phased-implementation-plan.md](rls-phased-implementation-plan.md)
