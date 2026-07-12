# Documentation Index

This folder contains architecture, implementation, operations, and RLS guidance for this Django SaaS ERP project.

## Start Here By Role

- Developer
  - [development-environment-setup-guide.md](development-environment-setup-guide.md)
  - [implementation-phases.md](implementation-phases.md)

- DevOps/SRE
  - [production-deployment-guide.md](production-deployment-guide.md)
  - [production-operations-runbook.md](production-operations-runbook.md)

- Backend/Data Modeler
  - [tenant-scoped-models-rls-guide.md](tenant-scoped-models-rls-guide.md)
  - [rls-enforcement-foundation.md](rls-enforcement-foundation.md)

- Architecture/Security Reviewer
  - [decisions/ADR-0001-tenancy-and-rls.md](decisions/ADR-0001-tenancy-and-rls.md)
  - [saas-erp-architecture-plan.md](saas-erp-architecture-plan.md)
  - [rls-multitenancy-guide.md](rls-multitenancy-guide.md)

- AI/Agent Contributor
  - [llm-agent-playbook.md](llm-agent-playbook.md)
  - [agent-memory.md](agent-memory.md)

## Documentation By Goal

- Understand platform architecture
  - [saas-erp-architecture-plan.md](saas-erp-architecture-plan.md)
  - [decisions/ADR-0001-tenancy-and-rls.md](decisions/ADR-0001-tenancy-and-rls.md)

- Execute delivery roadmap
  - [implementation-phases.md](implementation-phases.md)
  - [phase-11-14-roadmap.md](phase-11-14-roadmap.md)
  - [saas-product-audit.md](saas-product-audit.md)
  - [platform-admin-implementation-plan.md](platform-admin-implementation-plan.md)

- Build and validate RLS-safe tenant features
  - [tenant-scoped-models-rls-guide.md](tenant-scoped-models-rls-guide.md)
  - [rls-enforcement-foundation.md](rls-enforcement-foundation.md)
  - [rls-phased-implementation-plan.md](rls-phased-implementation-plan.md)
  - [rls-multitenancy-guide.md](rls-multitenancy-guide.md)

- Deploy and run in production
  - [production-deployment-guide.md](production-deployment-guide.md)
  - [production-operations-runbook.md](production-operations-runbook.md)

## Recommended Reading Paths

- New engineer onboarding path

1. [development-environment-setup-guide.md](development-environment-setup-guide.md)
2. [decisions/ADR-0001-tenancy-and-rls.md](decisions/ADR-0001-tenancy-and-rls.md)
3. [saas-erp-architecture-plan.md](saas-erp-architecture-plan.md)
4. [implementation-phases.md](implementation-phases.md)

- RLS deep-dive path

1. [rls-enforcement-foundation.md](rls-enforcement-foundation.md)
2. [tenant-scoped-models-rls-guide.md](tenant-scoped-models-rls-guide.md)
3. [rls-multitenancy-guide.md](rls-multitenancy-guide.md)
4. [rls-phased-implementation-plan.md](rls-phased-implementation-plan.md)

## Ownership

- Platform architecture: core engineering team
- Security controls: platform and security team
- AI/agent quality gates: AI platform team
