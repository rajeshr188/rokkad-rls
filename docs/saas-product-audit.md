# SaaS Product Audit

## Current Strengths

- Multi-workspace tenancy with PostgreSQL RLS isolation
- Global authentication with email verification
- Centralized authorization and role mapping
- Invitation lifecycle with replay and email-match protection
- Subscription domain models and feature gating
- Example tenant module with end-to-end tenancy pattern
- Health checks, rate limits, and CI baseline

## What Is Still Missing For A True SaaS Product

### Public Product Surface

- Public landing page
- Public pricing page
- Product positioning and feature comparison
- Public calls-to-action for signup and workspace creation

### Commercial Layer

- Customer-facing billing settings
- Upgrade and downgrade UX
- Checkout flow backed by a payment provider
- Invoices, billing history, and payment failure recovery
- Trial expiry and past-due UX

### Onboarding And Activation

- Guided first-workspace onboarding
- Team invite prompts during onboarding
- Better empty states for first-time users
- Workspace settings and account hub polish

### Operational SaaS Readiness

- Deployment and environment strategy
- Background email delivery and async jobs
- Error reporting, monitoring, backups, and restore process
- Support tooling for customer operations

### Product Completeness

- Non-owner member workspace switch/list strategy
- End-to-end browser/user-journey tests
- Coverage thresholds and performance baseline checks

## Recommended Next Build Order

1. Landing page and pricing page
2. Workspace billing settings and current plan UX
3. Provider-backed checkout plus webhook synchronization
4. Onboarding flow and workspace settings
5. Production operations and observability pipeline