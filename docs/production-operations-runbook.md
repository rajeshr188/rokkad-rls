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

## RLS Denial Observability And Alerts

Use this section to standardize production logging and alerting for PostgreSQL RLS denials.

### Structured Logging Schema

Emit one structured security event for every suspected RLS deny path.

Event name:

- `rls_access_denied`

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| event_name | string | Always `rls_access_denied` |
| timestamp | RFC3339 string | UTC event time |
| environment | string | prod, staging, dev |
| service | string | django-web, worker, webhook-consumer |
| request_id | string | Correlation id propagated through request lifecycle |
| actor_id | string or null | Authenticated user id if available |
| workspace_slug | string or null | Workspace slug from route context |
| workspace_id_context | string or null | Workspace id resolved server-side |
| db_role | string | Current PostgreSQL role used by runtime |
| http_method | string or null | GET, POST, PATCH, DELETE |
| route | string or null | Logical route name or path template |
| status_code | integer or null | HTTP response code |
| exception_class | string | Database exception class |
| sqlstate | string or null | PostgreSQL SQLSTATE when available |
| error_message | string | Sanitized error detail |
| source_ip | string or null | Client IP from trusted proxy chain |
| user_agent | string or null | Request user-agent |

Redaction requirements:

1. Never log raw secrets, tokens, webhook signatures, or credentials.
2. Never log full SQL text with embedded user payload values.
3. Keep payload fragments to allowlisted metadata only.

Retention and indexing:

1. Retain security events for at least 90 days online and 1 year archived.
2. Index by `event_name`, `environment`, `request_id`, `actor_id`, `workspace_slug`, `sqlstate`.

### Alert Specification

Define the following production alerts.

1. RLS deny rate spike
   - Condition: `rls_access_denied` count exceeds baseline threshold over 5 minutes.
   - Recommended threshold: warning at 20 events per 5 minutes, critical at 50 events per 5 minutes.
   - Group by: service and environment.

2. Actor abuse or automation pattern
   - Condition: single `actor_id` or `source_ip` emits repeated denials across multiple workspace slugs.
   - Recommended threshold: 10+ denials in 10 minutes touching 3+ workspace slugs.
   - Severity: critical.

3. Post-deploy regression detector
   - Condition: deny rate increases 3x over previous 24-hour baseline within 30 minutes of deploy.
   - Severity: warning, auto-escalate to critical if sustained for 15 minutes.

4. Critical route deny detector
   - Condition: any deny event from billing, memberships, invitation acceptance, or checkout webhook paths.
   - Severity: warning on first occurrence, critical for repeated occurrences.

Notification targets:

1. Warning: on-call Slack or Teams channel.
2. Critical: paging system plus incident channel creation.

### Incident Triage Playbook For RLS Denials

1. Verify deploy timeline and recent config changes.
2. Check runtime role posture and rerun strict gates:
   - `python manage.py check_rls --strict-privileges`
3. Confirm pooling mode matches documented context propagation contract.
4. Correlate events by `request_id` between app logs and database logs.
5. Identify whether source is legitimate user behavior, application regression, or abuse.
6. Apply mitigation: rollback, feature flag disablement, rate limit tightening, or credential rotation.
7. Record root cause and add follow-up regression test or guardrail.

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

### Ownership Drift SOP

Use this SOP when runtime role ownership, role privileges, or role-escalation posture drifts from the RLS baseline.

Detection checklist:

1. Runtime role must not be superuser.

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname = 'rls_app_runtime';
```

1. Runtime role must not be able to escalate to migration-owner role.

```sql
SELECT pg_has_role('rls_app_runtime', 'rls_migration_owner', 'MEMBER') AS runtime_can_escalate_to_migration_owner;
```

1. Runtime role must not own tenant tables.

```sql
SELECT
      c.relname AS table_name,
      pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind = 'r'
   AND n.nspname = 'public'
   AND c.relrowsecurity
   AND a.attname = 'workspace_id'
   AND NOT a.attisdropped
ORDER BY c.relname;
```

Immediate remediation order:

1. Stop rollout and freeze schema changes.
2. Remove runtime escalation posture:
   - revoke migration-owner membership from runtime role
   - ensure `rolsuper=false` and `rolbypassrls=false` for runtime role
3. Reassign tenant table ownership to migration-owner role.
4. Re-apply runtime DML grants only (no ownership, no superuser privileges).
5. Run strict checks with runtime credentials:
   - `python manage.py check_rls --strict-privileges`
6. Resume rollout only after checks pass and incident notes are captured.

Closure criteria:

1. Runtime role has `rolsuper=false` and `rolbypassrls=false`.
2. Runtime role cannot escalate to migration-owner role.
3. Runtime role owns zero tenant tables.
4. `check_rls --strict-privileges` passes in the affected environment.

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
