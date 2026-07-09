# Production Deployment Guide

This guide provides a production deployment checklist for the Django + PostgreSQL RLS architecture.

## 1. Deployment Prerequisites

- Production PostgreSQL instance
- HTTPS termination (load balancer/reverse proxy)
- Secret management (vault, parameter store, or equivalent)
- Process manager/runtime (systemd, container orchestration, or PaaS)
- Centralized logging and metrics

## 2. Required Environment Variables

Minimum:

```env
DJANGO_SECRET_KEY=<strong-random-secret>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<comma-separated-hosts>
DB_ENGINE=postgres
DB_NAME=<db-name>
DB_USER=<db-user>
DB_PASSWORD=<db-password>
DB_HOST=<db-host>
DB_PORT=5432
```

## 3. Database Role Setup Required For RLS Foundation

Use two PostgreSQL roles in production:

- migration/owner role:
  - owns tenant tables
  - executes migrations and policy DDL
- runtime app role:
  - used by Django runtime
  - must not own tenant tables
  - must not have `BYPASSRLS`
  - should only have required DML privileges

Recommended deployment practice:

1. run `migrate` with migration/owner role credentials
2. run app with runtime role credentials
3. run `python manage.py check_rls` using runtime role and fail deployment if it fails

### PostgreSQL Role Provisioning SQL Template

Use this as a starting point and adapt names/passwords/schema for your environment.

```sql
-- 1) Create dedicated roles.
CREATE ROLE rls_migration_owner LOGIN PASSWORD 'replace-owner-password';
CREATE ROLE rls_app_runtime LOGIN PASSWORD 'replace-runtime-password' NOBYPASSRLS;

-- 2) Grant database and schema usage.
GRANT CONNECT ON DATABASE rls_rokkad TO rls_app_runtime;
GRANT USAGE ON SCHEMA public TO rls_app_runtime;

-- 3) Ensure tenant tables are owned by migration role (not runtime role).
-- Run after migrations are executed by owner role or if ownership must be corrected.
REASSIGN OWNED BY rls_app_runtime TO rls_migration_owner;

-- 4) Grant runtime DML privileges only as needed.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rls_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rls_app_runtime;

-- 5) Ensure future tables/sequences created by owner role keep runtime grants.
ALTER DEFAULT PRIVILEGES FOR ROLE rls_migration_owner IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rls_app_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE rls_migration_owner IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO rls_app_runtime;
```

Recommended verification queries:

```sql
-- Runtime role must not bypass RLS.
SELECT rolname, rolbypassrls
FROM pg_roles
WHERE rolname IN ('rls_migration_owner', 'rls_app_runtime');

-- Runtime role should not own tenant tables.
SELECT n.nspname AS schema_name, c.relname AS table_name, pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
  AND c.relname IN (
    'notes_note',
    'memberships_workspacemember',
    'billing_subscription',
    'workspace_invitations_workspaceinvitation',
    'common_auditlog'
  );
```

### Phase 3 Strict Verification Procedure (copy/paste)

Run these checks in staging/production before finalizing deploy. Replace role names only if your environment uses different names.

```sql
-- A) Runtime role must exist and must not bypass RLS.
SELECT rolname, rolcanlogin, rolbypassrls
FROM pg_roles
WHERE rolname = 'rls_app_runtime';

-- Expected: one row with rolcanlogin=true and rolbypassrls=false.

-- B) Runtime role must not own tenant tables.
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
  AND c.relname IN (
      'notes_note',
      'memberships_workspacemember',
      'billing_subscription',
      'workspace_invitations_workspaceinvitation',
      'common_auditlog'
  )
ORDER BY c.relname;

-- Expected: owner is migration role (for example rls_migration_owner), never rls_app_runtime.

-- C) Tenant tables must have RLS and FORCE RLS enabled.
SELECT
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls_enabled
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
  AND c.relname IN (
      'notes_note',
      'memberships_workspacemember',
      'billing_subscription',
      'workspace_invitations_workspaceinvitation',
      'common_auditlog'
  )
ORDER BY c.relname;

-- Expected: rls_enabled=true and force_rls_enabled=true for every listed table.

-- D) Tenant tables must have at least one policy containing both USING and WITH CHECK.
SELECT
    schemaname,
    tablename,
    policyname,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN (
      'notes_note',
      'memberships_workspacemember',
      'billing_subscription',
      'workspace_invitations_workspaceinvitation',
      'common_auditlog'
  )
ORDER BY tablename, policyname;

-- Expected: each table has at least one policy with non-null qual and non-null with_check.
```

Then run strict application verification with runtime credentials:

```bash
python manage.py check
python manage.py check --deploy
python manage.py check_rls
```

Expected:

- `check_rls` exits successfully without `--allow-owned-tables`
- zero runtime role ownership findings
- no BYPASSRLS finding for runtime role

Security hardening (recommended):

```env
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SECURE_SSL_REDIRECT=true
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=true
SECURE_HSTS_PRELOAD=true
```

Billing configuration (if using SDK paths):

```env
BILLING_USE_SDK=true
BILLING_PROVIDER=stripe
BILLING_STRIPE_SECRET_KEY=<secret>
BILLING_STRIPE_PRICE_LOOKUP={"starter":"price_x","growth":"price_y"}
BILLING_WEBHOOK_SECRET_STRIPE=<webhook-secret>
```

or

```env
BILLING_USE_SDK=true
BILLING_PROVIDER=razorpay
BILLING_RAZORPAY_KEY_ID=<key-id>
BILLING_RAZORPAY_KEY_SECRET=<key-secret>
BILLING_RAZORPAY_PLAN_LOOKUP={"starter":"plan_x","growth":"plan_y"}
BILLING_WEBHOOK_SECRET_RAZORPAY=<webhook-secret>
```

## 4. Deployment Steps

1. Pull release artifact/image.
1. Install dependencies.
1. Run migrations using migration/owner role:

```bash
python manage.py migrate --noinput
```

1. Switch environment to runtime app role and run checks:

```bash
python manage.py check
python manage.py check --deploy
python manage.py check_rls
```

1. Start/roll app processes.
1. Verify health endpoint:

```bash
curl -f https://<host>/healthz/
```

## 5. Post-Deploy Validation

- Login/signup routes respond
- Workspace dashboard loads
- Billing pages load
- Webhook endpoint responds to signed test event
- No unexpected 5xx spikes
- `check_rls` passes under runtime role

## 6. Rollback Strategy

1. Roll app back to previous release version.
2. If migration rollback is required, run explicit reverse migration plan only after impact review.
3. Re-verify `/healthz/` and critical routes.

## 7. Operational Guardrails

- Never run production with `DJANGO_DEBUG=true`.
- Keep `DJANGO_SECRET_KEY` and DB credentials out of source control.
- Ensure TLS end-to-end from client to edge.
- Monitor webhook failures and replay/idempotency behavior.
- Never grant `BYPASSRLS` to runtime app role.
- Keep runtime role as non-owner of tenant tables.

## 8. CI/CD Expectations

- `manage.py check`
- `manage.py check --deploy`
- `manage.py check_rls`
- smoke tests
- full test suite with coverage gate

These are already represented in `.github/workflows/ci.yml`.
