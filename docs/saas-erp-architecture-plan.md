# SaaS ERP Architecture Plan (Django + PostgreSQL RLS)

## 1. Architecture Goals

- Shared-schema SaaS foundation for multiple workspaces
- Strict data isolation at database level
- Explicit, maintainable, production-ready logic
- Clear boundaries across authentication, tenancy, authorization, billing, and business apps
- Ready for future ERP modules: accounting, loans, inventory, sales, purchase, commodity, reports, customer portal

## 2. Core Stack

- Django
- PostgreSQL
- PostgreSQL Row Level Security (RLS)
- django-invitations
- Celery (for async jobs)

## 3. Design Principles

- Keep it simple and explicit
- Database-level isolation first
- Django-level authorization second
- No hidden magic tenancy behavior
- No schema-per-tenant complexity

## 4. Authentication (Global)

### What is global

- User account
- Password and login sessions
- Email verification status
- Password reset flow
- Profile data (name, timezone, locale)

### What is workspace-scoped

- Workspace role
- Workspace status
- Workspace-specific permissions and feature access

### Required flows

- Signup
- Login and logout
- Password reset
- Email verification
- Social login readiness via pluggable auth adapter (optional in first release)

## 5. Workspace Tenancy Model

### Core model

- `Workspace`: tenant boundary
- `WorkspaceMember`: user membership and role in workspace

### Workspace lifecycle

- User creates workspace and becomes owner
- User can belong to many workspaces
- User can switch active workspace

### Active workspace resolution

- Request middleware resolves active workspace
- Validate membership before setting workspace context
- Set `request.active_workspace`

### URL strategy

- Workspace-scoped routes under path prefix: `/w/{workspace_slug}/...`
- Global routes outside workspace prefix

## 6. PostgreSQL RLS Strategy

### Tenant table requirements

- `workspace_id` UUID NOT NULL FK to workspace
- Index on `workspace_id`
- RLS enabled and forced

### Session context

On each tenant request, set transaction-local variable:

`set_config('app.current_workspace_id', '<uuid>', true)`

### Policy shape

- `USING (workspace_id = current_setting('app.current_workspace_id', true)::uuid)`
- `WITH CHECK (workspace_id = current_setting('app.current_workspace_id', true)::uuid)`

### Safety defaults

- Missing `app.current_workspace_id` should deny access
- Never fall back to all workspaces

### Role model

- Migration role owns schema and policies
- Application role has no BYPASSRLS
- Platform admin actions use separate audited path

### Jobs and commands

- Celery task payload includes workspace_id for tenant tasks
- Task entrypoint sets DB workspace setting before querying tenant tables
- Management commands require explicit `--workspace` for tenant actions

## 7. Membership and Authorization

### Membership roles

- owner
- admin
- manager
- staff
- viewer
- future: customer_portal

### Authorization pattern

- Central policy service (single source of truth)
- Views call policy service, not ad hoc role checks
- Templates use permission helpers for UI visibility only

### Permission model

- Workspace-level permissions
- Domain permissions (for modules)
- Role-to-permission mapping defined in code first

## 8. Invitations (Custom RLS-First)

### Required behavior

- Invite existing or new user by email
- Assign role at invite time
- Pending invites list
- Revoke and resend
- Expiry handling
- Duplicate membership prevention
- Token acceptance must work with workspace-aware PostgreSQL RLS

### Acceptance flow

1. Validate token and expiry
2. Ensure accepting account email matches invite email
3. Create membership atomically if not already present
4. Mark invitation accepted

### Future Hybrid Option (if needed)

- Keep workspace invitation lifecycle, status model, and acceptance logic in `workspace_invitations`.
- Use `django-invitations` only for email dispatch and template rendering.
- Maintain RLS and membership write path in internal services to preserve tenant isolation guarantees.

## 9. Subscription and Billing

### Ownership

- Subscription belongs to workspace
- Owner is default payer

### Key entities

- Plan
- Subscription
- SubscriptionFeature

### States

- trialing
- active
- past_due
- canceled
- expired

### Enforcement

- Middleware for coarse access gate
- Service-level checks for feature and limit enforcement
- UI reflects state but does not enforce security

### Billing provider readiness

- Provider abstraction for Stripe and Razorpay
- Business apps consume feature service only

## 10. Tenant App Conventions

### Base model

- `TenantScopedModel` abstract class with workspace FK and timestamps

### Service pattern

- Services accept explicit `workspace` and `actor`
- No business logic in views

### Module enablement

- Feature key registry maps modules to subscription features
- Disabled modules return upgrade flow

## 11. Suggested Project Apps

- accounts
- workspaces
- memberships
- workspace_invitations
- authorization
- billing
- core
- common
- platform_admin
- tenant modules (future)

## 12. Request Lifecycle (Explicit)

1. User authenticates globally
2. User accesses workspace route
3. Middleware resolves workspace and validates membership
4. Middleware sets `request.active_workspace`
5. Middleware sets `app.current_workspace_id` in DB session
6. View calls authorization service
7. View or service calls subscription feature gate
8. Service runs tenant query
9. RLS enforces row isolation
10. Response rendered
11. Audit log written for sensitive events

## 13. UI and Routing Hierarchy

### Public

- Landing
- Pricing
- Signup
- Login

### Global authenticated

- Global dashboard
- Workspace list and switcher
- Create workspace
- Pending invitations
- Account settings

### Workspace Pages

- Workspace dashboard
- Members
- Invitations
- Roles and permissions
- Billing and subscription
- Settings
- Tenant module navigation

### Platform admin

- Workspaces
- Users
- Subscriptions
- Usage and support tools

## 14. Initial Data Model Plan

### User and profile

- User(email unique, is_active, is_verified)
- UserProfile(user, name, timezone, locale)

### Workspace

- Workspace(id UUID, name, slug unique, owner, status)

### Membership

- WorkspaceMember(workspace, user, role, status, joined_at)
- Unique(workspace, user)

### Invitation

- WorkspaceInvitation(workspace, email, role, invited_by, status, expires_at, token_ref)
- Unique pending invite guard per workspace and email

### Billing

- Plan(code unique, name, interval, base_price, seat_limit)
- Subscription(workspace, plan, state, trial_end, period bounds)
- SubscriptionFeature(plan, feature_key, is_enabled, limit_value)

### Audit

- AuditLog(actor, workspace, action, target_type, target_id, metadata, created_at)

### Base tenant model

- TenantScopedModel(workspace, timestamps, created_by optional)

## 15. Security Checklist

- RLS enabled and forced on all tenant tables
- App DB role without BYPASSRLS
- No tenant queries without active workspace context
- No all-tenant fallback paths in app code
- Membership validated on workspace requests
- Invitation flow secured by expiry and email binding
- Subscription checks enforced server-side
- Background tasks set workspace context explicitly
- Platform admin access is isolated and audited
- Isolation tests included for every tenant module

## 16. Risks and Tradeoffs

- Manual RLS has higher migration complexity but stronger control
- Shared schema is simple operationally but needs disciplined indexing
- Central policy service reduces drift but must be kept authoritative

## 17. Immediate Build Order

1. Foundation and settings split
2. Authentication
3. Workspaces and memberships
4. RLS middleware and policies
5. Invitations
6. Authorization module
7. Billing and subscription gates
8. Example tenant app
9. UI standardization
10. Hardening and test expansion
