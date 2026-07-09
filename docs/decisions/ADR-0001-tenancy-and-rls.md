# ADR-0001: Shared Schema Multitenancy with PostgreSQL RLS

## Status

Accepted

## Date

2026-07-07

## Context

The platform is a SaaS ERP foundation intended to host multiple tenant workspaces in one database while preserving strict data isolation. The product also needs simple and explicit code paths that remain understandable over time.

## Decision

Use a single shared PostgreSQL schema with `workspace_id` on every tenant-scoped table and enforce isolation using PostgreSQL Row Level Security (RLS).

## Rationale

- Strong isolation at database level
- Simple operational model compared to schema-per-tenant
- Explicit and auditable security rules
- Better developer ergonomics than hidden tenancy abstractions

## Consequences

### Positive

- Cross-tenant data leakage risk significantly reduced
- Tenancy logic is explicit in migrations and policies
- New apps follow a repeatable tenant model pattern

### Negative

- Requires discipline to add RLS for every new tenant table
- Migration and policy authoring overhead
- Requires robust policy tests

## Non-Goals

- Dynamic schema-per-tenant support
- Implicit magic tenancy injection via custom ORM hacks

## Implementation Notes

- Add `workspace_id` NOT NULL FK to all tenant tables
- Enable and force RLS for tenant tables
- Set transaction-local DB setting `app.current_workspace_id`
- Deny all access when workspace context is missing
- Keep application role without BYPASSRLS

## Review Trigger

Revisit this ADR only if one of the following is true:

- Hard compliance requirement demands physical tenant database separation
- Shared-schema performance becomes a proven blocker
- Regulatory or customer contracts require dedicated tenant infrastructure
