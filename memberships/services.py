from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from authorization.permissions import MEMBERSHIP_CHANGE_ROLE, MEMBERSHIP_MANAGE, MEMBERSHIP_VIEW
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context
from memberships.models import WorkspaceMember


def require_active_membership(*, actor, workspace) -> WorkspaceMember:
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    apply_workspace_context(workspace.id)

    try:
        return WorkspaceMember.objects.get(
            workspace=workspace,
            user=actor,
            status=WorkspaceMember.Status.ACTIVE,
        )
    except WorkspaceMember.DoesNotExist as exc:
        raise PermissionDenied("You are not an active member of this workspace.") from exc


def add_member(*, actor, workspace, payload: dict) -> WorkspaceMember:
    require_permission(actor=actor, workspace=workspace, permission=MEMBERSHIP_MANAGE)

    user = payload.get("user")
    role = payload.get("role", WorkspaceMember.Role.VIEWER)
    if not user:
        raise ValidationError({"user": "User is required."})
    if role not in WorkspaceMember.Role.values:
        raise ValidationError({"role": "Invalid role."})

    membership, created = WorkspaceMember.objects.get_or_create(
        workspace=workspace,
        user=user,
        defaults={
            "role": role,
            "status": WorkspaceMember.Status.ACTIVE,
            "invited_by": actor,
            "joined_at": timezone.now(),
        },
    )

    if not created and membership.status == WorkspaceMember.Status.ACTIVE:
        raise ValidationError("User is already an active member.")

    if not created:
        membership.role = role
        membership.status = WorkspaceMember.Status.ACTIVE
        membership.invited_by = actor
        membership.joined_at = timezone.now()
        membership.save(update_fields=["role", "status", "invited_by", "joined_at", "updated_at"])

    log_action(
        actor=actor,
        workspace=workspace,
        action="membership.created",
        target_type="WorkspaceMember",
        target_id=membership.id,
        metadata={
            "member_user_id": membership.user_id,
            "role": membership.role,
            "status": membership.status,
        },
    )

    return membership


def list_members(*, actor, workspace):
    require_permission(actor=actor, workspace=workspace, permission=MEMBERSHIP_VIEW)
    apply_workspace_context(workspace.id)
    return WorkspaceMember.objects.filter(workspace=workspace).select_related("user")


def get_member(*, actor, workspace, member_id):
    require_permission(actor=actor, workspace=workspace, permission=MEMBERSHIP_VIEW)
    apply_workspace_context(workspace.id)
    try:
        return WorkspaceMember.objects.get(workspace=workspace, id=member_id)
    except WorkspaceMember.DoesNotExist as exc:
        raise ValidationError("Member not found in workspace.") from exc


def change_member_role(*, actor, workspace, membership: WorkspaceMember, new_role: str) -> WorkspaceMember:
    require_permission(actor=actor, workspace=workspace, permission=MEMBERSHIP_CHANGE_ROLE)

    if membership.workspace_id != workspace.id:
        raise ValidationError("Membership does not belong to the active workspace.")
    if new_role not in WorkspaceMember.Role.values:
        raise ValidationError({"role": "Invalid role."})

    previous_role = membership.role
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    log_action(
        actor=actor,
        workspace=workspace,
        action="membership.role_updated",
        target_type="WorkspaceMember",
        target_id=membership.id,
        metadata={
            "member_user_id": membership.user_id,
            "previous_role": previous_role,
            "new_role": new_role,
        },
    )
    return membership
