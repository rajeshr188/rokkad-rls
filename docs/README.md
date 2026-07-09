# Documentation Index

This folder contains the baseline documentation for the Django SaaS ERP boilerplate with PostgreSQL Row Level Security (RLS) and agent-assisted development.

## Core Docs

- `saas-erp-architecture-plan.md`
  Full architecture blueprint, data model plan, RLS design, app boundaries, URL hierarchy, security checklist, and roadmap.

- `implementation-phases.md`
  Execution plan by phase with goals, deliverables, tests, and acceptance criteria.

- `llm-agent-playbook.md`
  LLM and agent operating model, guardrails, prompt contracts, evaluation strategy, and observability.

- `saas-product-audit.md`
  Productization audit covering missing commercial, onboarding, operational, and public SaaS surfaces.

- `phase-11-14-roadmap.md`
  Post-foundation roadmap for public product surface, billing UX, checkout/onboarding, and production operations.

- `production-operations-runbook.md`
  Deployment, monitoring, backup/restore, support operations, and CI quality gate runbook.

- `development-environment-setup-guide.md`
  Local development setup for Windows/macOS/Linux, environment variables, migrations, and troubleshooting.

- `production-deployment-guide.md`
  Production deployment checklist, secure environment settings, rollout, validation, and rollback guidance.

- `tenant-scoped-models-rls-guide.md`
  Patterns for designing tenant-scoped models, adding RLS migrations, and writing isolation tests.

- `rls-multitenancy-guide.md`
  Deep dive into how PostgreSQL RLS is used to enforce shared-schema multitenancy.

- `decisions/ADR-0001-tenancy-and-rls.md`
  Architecture Decision Record for shared-schema multitenancy with PostgreSQL RLS.

## How to Use

1. Read the ADR first to understand the core platform decision.
2. Use the architecture plan to implement foundational apps.
3. Follow the implementation phases to execute in sequence.
4. Apply the LLM-agent playbook for any AI or agent workflows.

## Ownership

- Platform architecture: core engineering team
- Security controls: platform and security team
- AI/agent quality gates: AI platform team
