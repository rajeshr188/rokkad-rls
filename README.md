# rls_rokkad Django Project

SaaS ERP boilerplate foundation using Django, PostgreSQL, and workspace-based multitenancy with PostgreSQL Row Level Security (RLS).

## Prerequisites

- Python 3.14+

## Setup

1. Create and activate virtual environment (already created as `.venv` in this workspace).
2. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Apply migrations:

   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   ```

4. Run the development server:

   ```powershell
   .\.venv\Scripts\python.exe manage.py runserver
   ```

## Environment File

- Local environment file: `.env`
- Template: `.env.example`
- The project automatically loads `.env` from the repository root.

## PostgreSQL Setup

1. Create database and user in PostgreSQL.
1. Create separate database roles for migration and runtime app access.

1. Update `.env` for runtime app role:

   - Set `DB_ENGINE=postgres`
   - Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

1. Run migrations with migration/owner role (recommended):

   ```powershell
   $env:DB_USER="<migration_owner_role>"
   $env:DB_PASSWORD="<migration_owner_password>"
   .\.venv\Scripts\python.exe manage.py migrate
   ```

1. Switch back to runtime app role and run checks:

   ```powershell
   $env:DB_USER="<runtime_app_role>"
   $env:DB_PASSWORD="<runtime_app_password>"
   .\.venv\Scripts\python.exe manage.py check
   .\.venv\Scripts\python.exe manage.py check_rls
   ```

RLS role safety baseline:

- runtime app role must not have `BYPASSRLS`
- runtime app role should not own tenant tables
- migration/owner role runs schema migrations and policy DDL

1. Validate configuration:

   ```powershell
   .\.venv\Scripts\python.exe manage.py check_rls
   ```

## Project Check

```powershell
.\.venv\Scripts\python.exe manage.py check
```

## Dev RLS Check Command

Run the development-stage RLS checklist with one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1
```

What it runs:

- `manage.py check`
- `manage.py makerlspolicies --dry-run`
- `manage.py check_rls --allow-owned-tables`

Optional strict baseline (informational in local environments):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1 -IncludeStrictCheck
```

Current local clean-state expectation:

- strict `check_rls` passes (no owner override)
- `--allow-owned-tables` remains available only as a diagnostic fallback

To make strict local `check_rls` pass, apply DB role hardening once with an admin account:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-dev-role-hardening.ps1 -AdminUser <postgres_admin_user> -AdminPassword <postgres_admin_password>
```

This command applies [scripts/dev-role-hardening.sql](scripts/dev-role-hardening.sql), then runs strict `check_rls` and the development RLS check bundle.

## Documentation

## Start Here

- Developer: [Development Environment Setup Guide](docs/development-environment-setup-guide.md)
- DevOps: [Production Deployment Guide](docs/production-deployment-guide.md) and [Production Operations Runbook](docs/production-operations-runbook.md)
- Backend/Data Modeler: [Tenant-Scoped Models and RLS Guide](docs/tenant-scoped-models-rls-guide.md)
- Security/Platform: [RLS Enforcement Foundation](docs/rls-enforcement-foundation.md)
- Architecture/Security Reviewer: [RLS Multitenancy Guide](docs/rls-multitenancy-guide.md), [Architecture Plan](docs/saas-erp-architecture-plan.md), and [ADR-0001](docs/decisions/ADR-0001-tenancy-and-rls.md)

## Full Documentation Map

- Docs index: [docs/README.md](docs/README.md)
- Architecture plan: [docs/saas-erp-architecture-plan.md](docs/saas-erp-architecture-plan.md)
- Implementation roadmap: [docs/implementation-phases.md](docs/implementation-phases.md)
- Development setup guide: [docs/development-environment-setup-guide.md](docs/development-environment-setup-guide.md)
- Production deployment guide: [docs/production-deployment-guide.md](docs/production-deployment-guide.md)
- Tenant-scoped models guide: [docs/tenant-scoped-models-rls-guide.md](docs/tenant-scoped-models-rls-guide.md)
- RLS enforcement foundation: [docs/rls-enforcement-foundation.md](docs/rls-enforcement-foundation.md)
- RLS multitenancy guide: [docs/rls-multitenancy-guide.md](docs/rls-multitenancy-guide.md)
- Production operations runbook: [docs/production-operations-runbook.md](docs/production-operations-runbook.md)
- LLM and agent playbook: [docs/llm-agent-playbook.md](docs/llm-agent-playbook.md)
- Architecture decision record: [docs/decisions/ADR-0001-tenancy-and-rls.md](docs/decisions/ADR-0001-tenancy-and-rls.md)
- Agent contributor guide: [AGENTS.md](AGENTS.md)
