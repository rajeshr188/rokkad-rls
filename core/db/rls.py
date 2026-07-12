from contextlib import ExitStack, contextmanager

from django.conf import settings
from django.db import connection


def _is_local_setting_enabled(local):
    if local is not None:
        requested_local = bool(local)
    else:
        requested_local = bool(getattr(settings, "RLS_CONTEXT_LOCAL", False))

    if not requested_local:
        return False

    # LOCAL settings only persist for a transaction. Under autocommit, outside
    # explicit atomic blocks, a LOCAL setting can be cleared before subsequent
    # ORM statements run.
    return bool(getattr(connection, "in_atomic_block", False))


def _set_rls_setting(*, setting_name: str, value: str, local=None) -> bool:
    if connection.vendor != "postgresql":
        return False

    is_local = _is_local_setting_enabled(local)
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, %s)", [setting_name, value, is_local])
    return True


def _reset_rls_setting(*, setting_name: str, local=None) -> bool:
    if connection.vendor != "postgresql":
        return False

    is_local = _is_local_setting_enabled(local)
    with connection.cursor() as cursor:
        if is_local:
            cursor.execute(f"SET LOCAL {setting_name} TO DEFAULT")
        else:
            cursor.execute(f"RESET {setting_name}")
    return True


def apply_workspace_context(workspace_id, *, local=None) -> bool:
    """Set DB workspace context for PostgreSQL-backed RLS checks and writes."""

    if workspace_id is None:
        return False

    setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
    return _set_rls_setting(setting_name=setting_name, value=str(workspace_id), local=local)


def clear_workspace_context(*, local=None) -> bool:
    setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
    return _reset_rls_setting(setting_name=setting_name, local=local)


def apply_actor_context(actor_id, *, local=None) -> bool:
    """Set DB actor context used by user-scoped RLS helper policies."""

    if actor_id is None:
        return False

    setting_name = "app.current_actor_id"
    return _set_rls_setting(setting_name=setting_name, value=str(actor_id), local=local)


def clear_actor_context(*, local=None) -> bool:
    return _reset_rls_setting(setting_name="app.current_actor_id", local=local)


def apply_invitation_token_context(token: str, *, local=None) -> bool:
    """Set DB invitation token context used by invitation acceptance RLS policy."""

    if not token:
        return False

    setting_name = "app.current_invitation_token"
    return _set_rls_setting(setting_name=setting_name, value=token, local=local)


def clear_invitation_token_context(*, local=None) -> bool:
    return _reset_rls_setting(setting_name="app.current_invitation_token", local=local)


@contextmanager
def workspace_context(workspace_id, *, local=None, clear_on_exit=True):
    """Temporarily apply workspace RLS context for non-request flows."""

    applied = apply_workspace_context(workspace_id, local=local)
    try:
        yield applied
    finally:
        if applied and clear_on_exit:
            clear_workspace_context(local=local)


@contextmanager
def actor_context(actor_id, *, local=None, clear_on_exit=True):
    """Temporarily apply actor RLS context for non-request flows."""

    applied = apply_actor_context(actor_id, local=local)
    try:
        yield applied
    finally:
        if applied and clear_on_exit:
            clear_actor_context(local=local)


@contextmanager
def invitation_token_context(token: str, *, local=None, clear_on_exit=True):
    """Temporarily apply invitation-token RLS context for non-request flows."""

    applied = apply_invitation_token_context(token, local=local)
    try:
        yield applied
    finally:
        if applied and clear_on_exit:
            clear_invitation_token_context(local=local)


@contextmanager
def tenant_context(*, workspace_id=None, actor_id=None, invitation_token=None, local=None):
    """Apply any combination of tenant RLS context keys within one scope."""

    with ExitStack() as stack:
        if actor_id is not None:
            stack.enter_context(actor_context(actor_id, local=local))
        if workspace_id is not None:
            stack.enter_context(workspace_context(workspace_id, local=local))
        if invitation_token:
            stack.enter_context(invitation_token_context(invitation_token, local=local))
        yield


def tenant_rls_sql(
    *,
    table_name: str,
    workspace_column: str = "workspace_id",
    setting_name: str = "app.current_workspace_id",
):
    """Return forward/reverse SQL for a standard workspace-isolation RLS policy."""

    policy_name = f"{table_name}_workspace_isolation"
    condition = (
        f"{workspace_column} = nullif(current_setting('{setting_name}', true), '')::uuid"
    )

    forward_sql = f"""
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name}
ON {table_name}
USING ({condition})
WITH CHECK ({condition});
""".strip()

    reverse_sql = f"""
DROP POLICY IF EXISTS {policy_name} ON {table_name};
ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;
""".strip()

    return forward_sql, reverse_sql
