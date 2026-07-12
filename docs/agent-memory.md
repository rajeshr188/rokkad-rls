# Agent Memory

Purpose: fast project context for LLMs and coding agents before making code changes.

## Project Snapshot

- Stack: Django, PostgreSQL, workspace-based multitenancy.
- Isolation model: shared schema with PostgreSQL RLS.
- Current priority: enforce tenant isolation and phased RLS hardening while progressing roadmap implementation.

## Non-Negotiable Constraints

- Tenant data isolation is enforced by PostgreSQL RLS.
- No tenant query execution without workspace context.
- No permission checks scattered across views.
- No direct business writes from AI prompts.
- New tenant business models must inherit TenantModel or TenantScopedModel.
- No tenant table changes without RLS migration coverage and passing check_rls.
- Runtime app role must not receive migration-owner privileges in CI or production.
- Runtime app role must not be superuser and must not be able to `SET ROLE` to migration-owner role.

## Required Inputs For Tenant Service Calls

Every tenant service call must include:

- actor
- workspace
- validated payload

For tenant writes, workspace DB context must be set before ORM access.

## RLS Runtime Context Keys

- app.current_workspace_id
- app.current_actor_id
- app.current_invitation_token

Set and clear through helpers and middleware in the core DB context layer.

## Required Validation Commands

Use this sequence for tenant model or policy changes:

1. python manage.py makemigrations
2. python manage.py makerlspolicies
3. python manage.py migrate
4. python manage.py check_rls
5. python manage.py check_rls --strict-privileges (CI/protected env gate)

Development bundled check:

- powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1 -IncludeStrictCheck

## File-Level Source Of Truth

- Agent rules: AGENTS.md
- AI safety and tooling contracts: docs/llm-agent-playbook.md
- RLS foundation controls: docs/rls-enforcement-foundation.md
- Tenant model implementation patterns: docs/tenant-scoped-models-rls-guide.md
- RLS architecture flow: docs/rls-multitenancy-guide.md
- Rollout status and evidence: docs/rls-phased-implementation-plan.md

## Change Protocol

When behavior or guardrails change, update this file in the same PR so future agents have current context.

Recent updates:

- CI role bootstrap tightened to keep runtime role least-privileged (no CREATEDB and no migration-role grant).
- Local role-hardening SQL now transfers ownership dynamically for RLS-enabled workspace tables instead of a static table list.
- `check_rls` now supports `--strict-privileges` to fail when runtime role is missing required DML grants.
- Role-safety docs now explicitly require runtime role `rolsuper=false` and no membership escalation to migration-owner role.
- Explicit RLS context manager utilities are available in `core.db.rls` (`workspace_context`, `actor_context`, `invitation_token_context`, `tenant_context`).
- Invitation acceptance service now uses context managers to scope and auto-clear invitation token and transaction-local workspace context.
- Production operations runbook now includes an explicit Ownership Drift SOP with detection SQL, remediation order, and closure criteria.
- RLS docs now explicitly keep `ATOMIC_REQUESTS=false` by default and require explicit `transaction.atomic()` boundaries for transaction-local context behavior.
