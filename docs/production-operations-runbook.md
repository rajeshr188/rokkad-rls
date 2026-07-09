# Production Operations Runbook

## Goal

Operational checklist for deploying, monitoring, and supporting the SaaS platform safely.

## Deployment Runbook

1. Validate environment variables:
   - `DJANGO_SECRET_KEY`
   - `DJANGO_DEBUG=false`
   - `DJANGO_ALLOWED_HOSTS`
   - `DB_ENGINE=postgres`
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
   - `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`
2. Validate database role model:
   - migration/owner role exists and owns tenant tables
   - runtime app role exists, does not own tenant tables, and does not have `BYPASSRLS`
3. Install dependencies:
   - `python -m pip install -r requirements.txt`
4. Run migrations using migration/owner role credentials:
   - `python manage.py migrate --noinput`
5. Switch to runtime app role credentials.
6. Run deployment smoke checks:
   - `python manage.py check --deploy`
   - `python manage.py check`
   - `python manage.py check_rls`
7. Run app smoke tests:
   - `python manage.py test core.tests.HealthEndpointTests workspaces.tests.WorkspaceCreatePageTests billing.tests.BillingProductSurfaceTests`

## Monitoring And Alerting Hooks

1. Health endpoint:
   - `GET /healthz/`
2. Alert on:
   - Health endpoint non-200
   - 5xx error rate spikes
   - Repeated billing webhook failures
   - Database connection failures
3. Log and retain:
   - Request errors
   - Billing webhook processing results
   - Audit log events for sensitive actions

## Phase 3 Role-Hardening Verification

Run this verification after deploy and during periodic security reviews.

1. Confirm runtime role cannot bypass RLS:

```sql
SELECT rolname, rolbypassrls
FROM pg_roles
WHERE rolname = 'rls_app_runtime';
```

Expected: `rolbypassrls=false`.

1. Confirm runtime role does not own tenant tables:

```sql
SELECT
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
```

Expected: owner is migration role for all listed tables.

1. Confirm strict checker still passes with runtime credentials:

```bash
python manage.py check_rls
```

Expected: success with no ownership or BYPASSRLS findings.

### Incident Response: Role Hardening Failure

If any check fails:

1. Stop rollout to production traffic.
2. Revert app credentials to last known-good runtime role (if changed).
3. Reassign table ownership back to migration role.
4. Re-run `python manage.py check_rls` before resuming rollout.
5. Record incident with root cause: credential drift, ownership drift, or role privilege drift.

## Backup And Restore

### Backup

1. Database backup cadence:
   - Daily full backup
   - Hourly WAL/incremental backup if available
2. Keep retention policy:
   - 30-day rolling backups minimum
3. Encrypt backups at rest and in transit.

### Restore Drill

1. Restore latest backup to staging environment.
2. Run:
   - `python manage.py migrate --noinput`
   - `python manage.py check`
3. Verify tenant isolation and key flows:
   - Workspace dashboard load
   - Billing page load
   - Invitation page load

## Support And Admin Operations

1. Use Django admin for controlled support operations.
2. Track sensitive actions via `AuditLog`.
3. Incident triage sequence:
   - Confirm impact scope (single workspace vs global)
   - Check recent deploys/migrations
   - Check billing webhook event failures
   - Mitigate and communicate

## CI Quality Gates

1. Coverage threshold enforced in CI (`COVERAGE_FAIL_UNDER`).
2. Smoke test suite runs in CI after migrations and checks.
3. Full Django test suite runs with coverage report output.
4. `python manage.py check_rls` runs in strict mode (no `--allow-owned-tables`) for protected environments.
