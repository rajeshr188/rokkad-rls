from django.core.exceptions import PermissionDenied

from authorization.permissions import ROLE_PERMISSIONS
from core.db import apply_workspace_context
from memberships.models import WorkspaceMember


def get_active_membership(*, actor, workspace):
    if not actor or not actor.is_authenticated:
        return None

    apply_workspace_context(workspace.id)

    return WorkspaceMember.objects.filter(
        workspace=workspace,
        user=actor,
        status=WorkspaceMember.Status.ACTIVE,
    ).first()


def has_permission(*, actor, workspace, permission: str) -> bool:
    membership = get_active_membership(actor=actor, workspace=workspace)
    if membership is None:
        return False

    role_permissions = ROLE_PERMISSIONS.get(membership.role, set())
    return permission in role_permissions


def require_permission(*, actor, workspace, permission: str) -> None:
    if not has_permission(actor=actor, workspace=workspace, permission=permission):
        raise PermissionDenied("You do not have permission to perform this action.")
