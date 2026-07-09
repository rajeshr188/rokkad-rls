# Development Environment Setup Guide

This guide explains how to set up the project for local development on Windows, macOS, or Linux.

## 1. Prerequisites

- Python 3.14+
- Git
- PostgreSQL 15+ (recommended for full RLS behavior)
- Optional: VS Code + Python extension

## 2. Clone And Create Virtual Environment

```bash
git clone <your-repo-url>
cd rls_rokkad
python -m venv .venv
```

Activate venv:

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure Environment Variables

Create `.env` in project root.

Example (SQLite quick start):

```env
DJANGO_SECRET_KEY=change-me-locally
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=sqlite
```

Example (PostgreSQL full behavior):

```env
DJANGO_SECRET_KEY=change-me-locally
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DB_ENGINE=postgres
DB_NAME=rls_rokkad
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
```

Recommended local role model for RLS parity with production:

- `migration_owner` role: runs migrations and owns tenant tables
- `runtime_app` role: used by Django app at runtime and must not own tenant tables
- runtime role must not have `BYPASSRLS`

Optional billing SDK settings (keep disabled unless needed):

```env
BILLING_USE_SDK=false
BILLING_PROVIDER=mock
```

## 4. Database Setup

### PostgreSQL

1. Create database and two roles:
   - migration/owner role
   - runtime app role
2. Grant runtime role only required DML privileges.
3. Confirm `.env` points to runtime role for normal app/test runs.

Role-aware migration workflow (PowerShell example):

```powershell
# Use migration owner only while running schema/policy migrations
$env:DB_USER="migration_owner"
$env:DB_PASSWORD="<migration_owner_password>"
python manage.py migrate

# Switch back to runtime app role for normal checks/tests
$env:DB_USER="runtime_app"
$env:DB_PASSWORD="<runtime_app_password>"
python manage.py check
python manage.py check_rls --allow-owned-tables
```

### Apply Migrations

```bash
python manage.py migrate
```

## 5. Run The App

```bash
python manage.py runserver
```

Open app at `http://127.0.0.1:8000`.

## 6. Run Quality Checks

```bash
python manage.py check
python manage.py test billing workspaces core memberships
python manage.py check_rls --allow-owned-tables
```

One-command local RLS workflow (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1
```

One-time local owner/runtime split (requires PostgreSQL admin account):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-dev-role-hardening.ps1 -AdminUser <postgres_admin_user> -AdminPassword <postgres_admin_password>
```

This applies [scripts/dev-role-hardening.sql](scripts/dev-role-hardening.sql) and verifies strict `check_rls`.

Optional strict baseline snapshot:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-dev-rls-checks.ps1 -IncludeStrictCheck
```

Coverage run:

```bash
coverage run --source='.' manage.py test
coverage report
```

## 7. Recommended Local Workflow

1. Create/activate virtual environment.
2. Pull latest changes.
3. Install dependencies if `requirements.txt` changed.
4. Run `migrate`.
5. Run `scripts/run-dev-rls-checks.ps1` for local RLS verification.
6. Run targeted tests for touched apps.
7. Run `manage.py check` before commit.

## 8. Common Issues

### `check --deploy` warnings in local environment

Local development intentionally often uses:

- `DEBUG=true`
- insecure cookies
- relaxed SSL settings

This is expected locally. Enforce production-safe values in production environment variables.

### PostgreSQL-specific RLS behavior not visible in SQLite

RLS isolation and session settings are PostgreSQL features. For full multitenancy validation, run local PostgreSQL.

### `check_rls` fails on table ownership in local setup

Current expected local baseline in this repository is strict `check_rls` pass.

If strict `check_rls` fails, treat it as drift (runtime role ownership, role grants, or policy regression).

Use either:

- re-apply proper local role separation (recommended), or
- temporary local-only override: `python manage.py check_rls --allow-owned-tables`

Do not use `--allow-owned-tables` in staging/production CI gates.

### Billing SDK errors

If `BILLING_USE_SDK=true`, missing provider credentials or plan/price mappings will raise validation errors. For most local development, keep `BILLING_USE_SDK=false`.
