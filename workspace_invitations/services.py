from datetime import timedelta
import secrets

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from authorization.permissions import INVITATION_MANAGE, INVITATION_VIEW
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context, invitation_token_context, tenant_context
from memberships.models import WorkspaceMember
from workspace_invitations.models import WorkspaceInvitation


DEFAULT_INVITATION_TTL_DAYS = 7


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _new_invite_expiry(*, ttl_days: int = DEFAULT_INVITATION_TTL_DAYS):
    return timezone.now() + timedelta(days=ttl_days)


def _new_invite_token() -> str:
    return secrets.token_urlsafe(32)


def list_invitations(*, actor, workspace):
    require_permission(actor=actor, workspace=workspace, permission=INVITATION_VIEW)
    apply_workspace_context(workspace.id)
    return WorkspaceInvitation.objects.filter(workspace=workspace).select_related("invited_by", "accepted_by")


def create_invitation(*, actor, workspace, payload: dict) -> WorkspaceInvitation:
    require_permission(actor=actor, workspace=workspace, permission=INVITATION_MANAGE)

    email = _normalize_email(payload.get("email"))
    role = payload.get("role") or WorkspaceMember.Role.VIEWER

    if not email:
        raise ValidationError({"email": "Email is required."})
    if role == WorkspaceMember.Role.OWNER:
        raise ValidationError({"role": "Owner role cannot be assigned via invitation."})
    if role not in WorkspaceMember.Role.values:
        raise ValidationError({"role": "Invalid role."})

    apply_workspace_context(workspace.id)

    if WorkspaceInvitation.objects.filter(workspace=workspace, email=email, status=WorkspaceInvitation.Status.PENDING).exists():
        raise ValidationError("A pending invitation already exists for this email.")

    if WorkspaceMember.objects.filter(
        workspace=workspace,
        user__email__iexact=email,
        status=WorkspaceMember.Status.ACTIVE,
    ).exists():
        raise ValidationError("This email already belongs to an active workspace member.")

    invitation = WorkspaceInvitation.objects.create(
        workspace=workspace,
        email=email,
        role=role,
        invited_by=actor,
        token=_new_invite_token(),
        expires_at=_new_invite_expiry(),
        last_sent_at=timezone.now(),
    )

    log_action(
        actor=actor,
        workspace=workspace,
        action="invitation.created",
        target_type="WorkspaceInvitation",
        target_id=invitation.id,
        metadata={"email": invitation.email, "role": invitation.role},
    )

    return invitation


def get_invitation(*, actor, workspace, invitation_id) -> WorkspaceInvitation:
    require_permission(actor=actor, workspace=workspace, permission=INVITATION_VIEW)
    apply_workspace_context(workspace.id)
    try:
        return WorkspaceInvitation.objects.get(workspace=workspace, id=invitation_id)
    except WorkspaceInvitation.DoesNotExist as exc:
        raise ValidationError("Invitation not found in workspace.") from exc


def revoke_invitation(*, actor, workspace, invitation: WorkspaceInvitation) -> WorkspaceInvitation:
    require_permission(actor=actor, workspace=workspace, permission=INVITATION_MANAGE)
    if invitation.workspace_id != workspace.id:
        raise ValidationError("Invitation does not belong to active workspace.")
    if invitation.status != WorkspaceInvitation.Status.PENDING:
        raise ValidationError("Only pending invitations can be revoked.")

    apply_workspace_context(workspace.id)
    invitation.status = WorkspaceInvitation.Status.REVOKED
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["status", "revoked_at", "updated_at"])

    log_action(
        actor=actor,
        workspace=workspace,
        action="invitation.revoked",
        target_type="WorkspaceInvitation",
        target_id=invitation.id,
        metadata={"email": invitation.email},
    )

    return invitation


def resend_invitation(*, actor, workspace, invitation: WorkspaceInvitation) -> WorkspaceInvitation:
    require_permission(actor=actor, workspace=workspace, permission=INVITATION_MANAGE)
    if invitation.workspace_id != workspace.id:
        raise ValidationError("Invitation does not belong to active workspace.")
    if invitation.status != WorkspaceInvitation.Status.PENDING:
        raise ValidationError("Only pending invitations can be resent.")

    apply_workspace_context(workspace.id)
    invitation.token = _new_invite_token()
    invitation.expires_at = _new_invite_expiry()
    invitation.last_sent_at = timezone.now()
    invitation.resend_count += 1
    invitation.save(update_fields=["token", "expires_at", "last_sent_at", "resend_count", "updated_at"])

    log_action(
        actor=actor,
        workspace=workspace,
        action="invitation.resent",
        target_type="WorkspaceInvitation",
        target_id=invitation.id,
        metadata={"email": invitation.email, "resend_count": invitation.resend_count},
    )

    return invitation


def accept_invitation(*, actor, token: str):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    with invitation_token_context(token):
        invitation = WorkspaceInvitation.objects.select_related("workspace").filter(token=token).first()
        if invitation is None:
            raise ValidationError("Invitation token is invalid.")

        if invitation.status != WorkspaceInvitation.Status.PENDING:
            raise ValidationError("Invitation token has already been used.")

        if invitation.expires_at <= timezone.now():
            invitation.status = WorkspaceInvitation.Status.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
            raise ValidationError("Invitation token has expired.")

        actor_email = _normalize_email(getattr(actor, "email", ""))
        if not actor_email or actor_email != invitation.email:
            raise PermissionDenied("Invitation email does not match authenticated account email.")

        with transaction.atomic():
            with tenant_context(workspace_id=invitation.workspace_id, local=True):
                membership, created = WorkspaceMember.objects.get_or_create(
                    workspace=invitation.workspace,
                    user=actor,
                    defaults={
                        "role": invitation.role,
                        "status": WorkspaceMember.Status.ACTIVE,
                        "invited_by": invitation.invited_by,
                        "joined_at": timezone.now(),
                    },
                )

                if not created:
                    membership.role = invitation.role
                    membership.status = WorkspaceMember.Status.ACTIVE
                    membership.invited_by = invitation.invited_by
                    membership.joined_at = membership.joined_at or timezone.now()
                    membership.save(update_fields=["role", "status", "invited_by", "joined_at", "updated_at"])

                invitation.status = WorkspaceInvitation.Status.ACCEPTED
                invitation.accepted_by = actor
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])

    with tenant_context(workspace_id=invitation.workspace_id):
        log_action(
            actor=actor,
            workspace=invitation.workspace,
            action="invitation.accepted",
            target_type="WorkspaceInvitation",
            target_id=invitation.id,
            metadata={"email": invitation.email, "membership_user_id": membership.user_id},
        )

    return invitation, membership
