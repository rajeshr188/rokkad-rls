# Platform Admin Implementation Plan

## Purpose

Define a minimal, secure first implementation of platform-level administration without weakening tenant RLS isolation.

## Scope For Phase 1

In scope:

1. Platform admin access model and permission checks.
2. Read-only platform admin views for global entities.
3. Audited platform admin actions.
4. RLS-safe operational patterns and explicit constraints.

Out of scope:

1. Bulk tenant data mutation tools.
2. Direct SQL execution from admin UI.
3. Cross-tenant write operations without additional approval workflow.

## Core Design Principles

1. Platform admin path is isolated from tenant UX and tenant APIs.
2. Tenant RLS remains the default isolation boundary.
3. Platform admin reads/writes are explicitly permission-gated and audited.
4. High-risk actions require explicit confirmation and incident traceability.

## Minimal Role Model

1. `platform_admin` capability (application-level policy), independent from workspace roles.
2. No automatic elevation from workspace owner/admin to platform admin.
3. Runtime DB role still follows RLS safety constraints:
   - no BYPASSRLS
   - no superuser
   - no migration-owner escalation

## Data And Access Boundaries

1. Keep platform admin metadata in non-tenant/global tables.
2. Do not bypass RLS on tenant tables by default.
3. For cross-tenant support lookups, require explicit target workspace selection and log every lookup.
4. Never accept user-supplied `workspace_id` as authority; resolve target workspace server-side.

## Initial Feature Set

1. Platform dashboard:
   - total active workspaces
   - total users
   - subscription state distribution
2. Workspace directory (read-only):
   - name, slug, status, owner, created_at
3. User directory (read-only):
   - id, email, active status, created_at
4. Subscription overview (read-only):
   - workspace, plan, state, period dates
5. Support lookup action:
   - require explicit workspace selection
   - write immutable audit event

## Service Layer Contract

Every platform-admin service call must include:

1. actor
2. validated payload
3. explicit policy check for platform-admin permission

For any tenant-scoped read/write within platform-admin workflows:

1. apply explicit context manager (`tenant_context`, `workspace_context`, etc.)
2. clear context automatically via context manager exit
3. emit audit log with actor, target workspace, action, reason

## Routing And App Structure

1. Keep platform-admin routes under a dedicated namespace (for example `/platform-admin/`).
2. Add dedicated decorators/policies for platform-admin access.
3. Keep business logic in `platform_admin/services.py`.
4. Keep views thin and policy-first.

## Audit And Observability Requirements

For every platform-admin action log:

1. actor_id
2. action name
3. target type and id
4. workspace_id when applicable
5. reason/metadata
6. request_id correlation

Alerting requirements:

1. repeated denied platform-admin attempts
2. unusual spike in cross-tenant support lookups
3. high-risk action attempts outside approved change windows

## Security Guardrails

1. No direct business writes from platform admin UI in Phase 1.
2. No hidden fallback that queries all tenant rows without explicit context.
3. High-risk operations require secondary confirmation.
4. Add rate limiting for platform-admin endpoints.

## Test Plan (Minimum)

1. Non-platform users receive 403 on all platform-admin endpoints.
2. Platform-admin read endpoints succeed and are audited.
3. Tenant lookup requires explicit workspace target.
4. Audit events are created for every platform-admin action.
5. No user-supplied workspace override is accepted.
6. RLS regression tests ensure tenant isolation is preserved.

## Rollout Steps

1. Add policy/decorator layer for platform-admin permission.
2. Implement read-only services and endpoints.
3. Add audit logging and observability hooks.
4. Add tests and CI coverage gates.
5. Enable feature behind a runtime flag in non-prod first.

## Exit Criteria

1. Platform-admin endpoints are isolated and permission-gated.
2. All actions are auditable and queryable by request_id.
3. No RLS safety gate regressions (`check_rls --strict-privileges` passes).
4. Security review confirms no cross-tenant leakage path.
