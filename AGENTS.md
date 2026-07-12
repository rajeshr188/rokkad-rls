# Agent Development Guide

This repository supports human and AI-assisted development. Follow these rules when implementing features.

## Non-Negotiable Rules

- Tenant data isolation is enforced by PostgreSQL RLS
- No tenant query execution without workspace context
- No permission checks scattered across random views
- No direct business writes from AI prompts
- Tenant business models must inherit `TenantModel`/`TenantScopedModel` (or be explicitly marked transitional)
- No PR introducing tenant tables without RLS migration coverage and passing `check_rls`

## Required Inputs for Service Calls

Every tenant service call must receive:

- actor (authenticated user)
- workspace (active workspace object)
- validated input payload

And for tenant writes:

- workspace context must be applied in DB session/transaction before ORM access

## Implementation Standards

- Keep business logic in services, not views
- Keep models explicit and small
- Add tests for role and workspace isolation on every new tenant model
- Add audit logs for sensitive operations
- Use `EnableRLS` migration operation for new tenant tables
- Use `makerlspolicies` after `makemigrations` to detect/generate missing policy migrations
- Ensure `check_rls` passes before merge/deploy

## AI and Agent Tooling Standards

- Tools are allowlisted and permission-aware
- Tools require workspace_id input
- High-risk actions require explicit user confirmation
- Tool actions must be logged with actor and workspace

## Code Review Checklist

- Does this tenant table include workspace_id and RLS migration?
- Are permission checks implemented via central authorization service?
- Are subscription feature gates enforced server-side?
- Are cross-workspace access tests included?
- Did `python manage.py makerlspolicies --dry-run` return cleanly?
- Did `python manage.py check_rls` pass in strict mode?
- Is runtime DB role configured without `BYPASSRLS` and without owning tenant tables?

## Pull Request Expectations

- Include migration notes when RLS policies are added or modified
- Include security test coverage for tenant isolation
- Include clear rollback notes for billing or auth changes
- If tenant guardrails, workflows, or validation commands changed, update `docs/agent-memory.md` in the same PR

## RLS Foundation Commands

Use this workflow for tenant model changes:

1. `python manage.py makemigrations`
2. `python manage.py makerlspolicies`
3. `python manage.py migrate`
4. `python manage.py check_rls`

Reference docs:

- `docs/rls-enforcement-foundation.md`
- `docs/rls-phased-implementation-plan.md`
- `docs/agent-memory.md`
