# Phase 11-14 Roadmap

## Phase 11: Public SaaS Surface

- Goal: Expose a public-facing product shell that explains the product and drives signups.
- Build:
  - Landing page
  - Pricing page
  - Public marketing navigation
  - Authenticated CTA routing into workspace flow
- Tests:
  - Public page render tests
  - Anonymous vs authenticated CTA behavior
- Acceptance criteria:
  - Anonymous visitors can understand the product and reach signup or pricing in one click.

## Phase 12: Billing UX And Catalog

- Goal: Expose customer-facing billing and plan management on top of the existing subscription domain.
- Build:
  - Workspace billing settings page
  - Plan catalog presentation
  - Upgrade/downgrade UX placeholder actions
  - Subscription status and trial visibility
- Tests:
  - Billing page access by role
  - Plan/status rendering tests
  - Plan-change action tests
- Acceptance criteria:
  - Workspace owners/admins can see current subscription state and available plans.

## Phase 13: Checkout And Onboarding

- Goal: Convert the internal billing model into a self-serve acquisition and activation flow.
- Build:
  - Payment provider abstraction endpoints
  - Checkout session creation
  - Webhook synchronization
  - First-workspace onboarding and invite prompts
- Current status:
  - Provider contract scaffold implemented with mock provider
  - Stripe-style and Razorpay-style provider adapter scaffolds implemented
  - SDK-backed Stripe and Razorpay checkout execution paths implemented behind `BILLING_USE_SDK`
  - Workspace checkout-session API endpoint implemented
  - Workspace checkout success callback endpoint implemented
  - Global webhook receiver endpoint implemented with idempotency persistence
  - Webhook signature verification enabled with provider-specific secrets
  - Workspace onboarding-ready marker and dashboard invite prompt implemented
  - Explicit onboarding completion action implemented from workspace dashboard
  - Onboarding completion telemetry is persisted in workspace metadata and audit logs
  - Checkout-session to webhook-activation flow is covered by tests
- Tests:
  - Webhook contract tests
  - Checkout/session authorization tests
  - First-run onboarding flow tests
- Acceptance criteria:
  - A new user can sign up, create a workspace, choose a plan, and begin onboarding.

- Remaining to close Phase 13:
  - Execute end-to-end in non-test environments with real provider credentials and plan/price mappings (deferred for now)

## Phase 14: Production Operations

- Goal: Make the product operationally ready for customers.
- Current status:
  - Production operations runbook added (deployment, monitoring, backup/restore, support operations)
  - CI coverage threshold gate added
  - CI smoke tests added
- Build:
  - Deployment and environment runbooks
  - Monitoring and alerting hooks
  - Backup and restore procedures
  - Support/admin operations surfaces
  - Coverage thresholds and browser smoke tests
- Tests:
  - Deployment smoke checks
  - Coverage gate in CI
  - End-to-end happy path tests
- Acceptance criteria:
  - The SaaS product can be deployed, observed, and supported with clear operational safeguards.
