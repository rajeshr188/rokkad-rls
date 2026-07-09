# Implementation Phases

## Phase 1: Project Foundation

- Goal: Create a clean project baseline with explicit app boundaries and coding standards.
- Files and apps: core, common, platform_admin, settings split.
- Build:
  - Create baseline apps and settings modules.
  - Add logging, error handling, and base abstract models.
  - Add audit utility and health endpoint.
- Tests:
  - App startup smoke tests.
  - Settings import tests.
  - Health endpoint test.
- Acceptance criteria:
  - Project boots in development and CI.
  - Baseline docs are present.
- Risks to avoid:
  - Premature abstraction in common utilities.

## Phase 2: Authentication

- Goal: Implement robust global account lifecycle.
- Files and apps: accounts.
- Build:
  - User registration, login, logout.
  - Email verification and password reset.
  - Profile management.
- Tests:
  - Signup and login flows.
  - Verification-required routes.
  - Password reset flow.
- Acceptance criteria:
  - Global auth flow is production-grade and reliable.
- Risks to avoid:
  - Mixing workspace checks into global auth views.

## Phase 3: Workspaces and Memberships

- Goal: Establish tenant boundary and role-bearing membership.
- Files and apps: workspaces, memberships.
- Build:
  - Workspace model and create flow.
  - Membership and role assignment.
  - Workspace switcher and active workspace storage.
- Tests:
  - Multi-workspace user scenarios.
  - Membership-required access checks.
- Acceptance criteria:
  - Active workspace resolves correctly per request.
- Risks to avoid:
  - Ambiguous workspace state handling.

## Phase 4: PostgreSQL RLS Foundation

- Goal: Guarantee tenant isolation at database layer.
- Files and apps: core and common migrations, middleware.
- Build:
  - Tenant-scoped model conventions.
  - SQL migrations to enable, force, and define RLS policies.
  - Middleware to set DB workspace session context.
- Tests:
  - Cross-tenant read and write denial tests.
  - Missing workspace context denial tests.
- Acceptance criteria:
  - No cross-workspace data access is possible.
- Risks to avoid:
  - Missing policy on new tenant tables.

## Phase 5: Invitations

- Goal: Support secure membership onboarding.
- Files and apps: workspace_invitations (custom RLS-first implementation).
- Build:
  - Workspace invitation model and lifecycle.
  - Invite existing/new users.
  - Accept, revoke, resend workflows.
  - Enforce email-match and replay-safe acceptance with workspace-aware DB context.
- Tests:
  - Token expiry and replay resistance.
  - Duplicate invite and duplicate membership prevention.
- Acceptance criteria:
  - Users can securely join through invitations.
- Risks to avoid:
  - Email mismatch acceptance vulnerabilities.

### Future Alternative (Option 2: Hybrid)

- Keep `workspace_invitations` as the domain source of truth (workspace, role, status, audit, RLS policy).
- Optionally adopt `django-invitations` only for outbound invitation delivery and email template handling.
- Do not replace workspace acceptance and membership provisioning logic in services.

## Phase 6: Authorization

- Goal: Centralize role and permission checks.
- Files and apps: authorization.
- Build:
  - Permission constants and role maps.
  - Policy service and reusable decorators/mixins.
  - Template permission helper tags.
- Tests:
  - Permission matrix tests by role.
- Acceptance criteria:
  - One policy source is used by views and services.
- Risks to avoid:
  - Scattered custom role checks.

## Phase 7: Subscription Management

- Goal: Tie plan, features, and limits to each workspace.
- Files and apps: billing.
- Build:
  - Plan, subscription, and feature models.
  - Trial and billing state transitions.
  - Feature and seat-limit enforcement.
  - Provider interface for Stripe and Razorpay.
- Tests:
  - Subscription state transitions.
  - Feature gate and limit checks.
- Acceptance criteria:
  - Module access reflects workspace subscription state.
- Risks to avoid:
  - Billing provider logic leaking into domain apps.

## Phase 8: Example Tenant Module

- Goal: Prove the boilerplate end-to-end with one module.
- Files and apps: notes or customers module.
- Build:
  - CRUD services and views.
  - Permission and feature gate integration.
  - RLS policy on module table.
- Tests:
  - Cross-tenant isolation tests.
  - Role and feature enforcement tests.
- Acceptance criteria:
  - Module demonstrates complete tenancy pattern.
- Risks to avoid:
  - Bypassing services with direct ORM usage in views.

## Phase 9: UI and Navigation Standards

- Goal: Create coherent global and workspace navigation.
- Files and apps: shared templates and navigation registry.
- Build:
  - Public, global authenticated, and workspace shells.
  - Role-aware and plan-aware navigation visibility.
- Tests:
  - Navigation visibility by role and plan.
- Acceptance criteria:
  - Users see only relevant and accessible actions.
- Risks to avoid:
  - UI-only hiding without backend enforcement.

## Phase 10: Hardening and Quality Gates

- Goal: Prepare for production reliability and security.
- Files and apps: all modules.
- Build:
  - Security headers and rate limits.
  - Audit log expansion.
  - CI quality gates and coverage thresholds.
- Tests:
  - End-to-end workflow tests.
  - Security and isolation regression tests.
  - Performance baseline tests.
- Acceptance criteria:
  - Security checklist is fully green.
  - Release candidate stability is achieved.
- Risks to avoid:
  - Missing negative tests for isolation and privilege bypass.

## Phase 11-14: Productization Roadmap Status

- Public SaaS surface and billing UX baseline are implemented.
- Phase 1 completion update:
  - Settings import smoke tests are now covered in automated tests.
- Phase 3 completion update:
  - Workspace listing/switcher now includes active memberships, not only ownership.
- Phase 4 completion update:
  - PostgreSQL RLS integration tests now cover memberships, notes, and billing subscriptions.
- Phase 7 completion update:
  - Provider interface now has mock, Stripe-style, and Razorpay-style adapters with signature verification hooks.
- Phase 13 foundation in progress:
  - Provider abstraction is wired with a mock provider.
  - Stripe-style provider adapter scaffold is wired for checkout session and webhook normalization.
  - Checkout session API is available per workspace.
  - Webhook synchronization is implemented with idempotency storage.
  - Webhook signature verification hooks are enforced when `BILLING_WEBHOOK_SECRET` is configured.
- Remaining for full Phase 13:
  - Real provider adapters (Stripe/Razorpay).
  - Onboarding prompt flow after successful checkout.
  - End-to-end checkout-to-activation tests.
