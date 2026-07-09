## Summary
- 

## Why
- 

## Scope
- [ ] Code changes are limited to the intended scope
- [ ] No unrelated refactors are included

## Security and Data Isolation
- [ ] No cross-workspace data access paths introduced
- [ ] Tenant-scoped writes are workspace-bound
- [ ] Raw SQL paths remain RLS-safe
- [ ] No secrets or credentials were added

## Database and Migrations
- [ ] Migration included (if schema changed)
- [ ] RLS policy migration included for new tenant models
- [ ] manage.py makerlspolicies --check passes
- [ ] manage.py check_rls passes

## Testing
- [ ] Added or updated tests for behavior changes
- [ ] Local tests pass
- [ ] CI checks pass

## Deployment Notes
- [ ] Backward-compatible change
- [ ] Rollback plan documented (if needed)

## Screenshots / Evidence (if applicable)
- 
