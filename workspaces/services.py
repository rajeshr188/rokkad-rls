from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from authorization.permissions import WORKSPACE_ACCESS
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context
from memberships.models import WorkspaceMember
from workspaces.models import Workspace


def _build_unique_slug(name: str) -> str:
    base_slug = slugify(name) or "workspace"
    candidate = base_slug
    counter = 1
    while Workspace.objects.filter(slug=candidate).exists():
        counter += 1
        candidate = f"{base_slug}-{counter}"
    return candidate


def create_workspace(*, actor, payload: dict) -> Workspace:
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError({"name": "Workspace name is required."})

    workspace = Workspace.objects.create(
        name=name,
        slug=_build_unique_slug(name),
        owner=actor,
    )

    apply_workspace_context(workspace.id)

    WorkspaceMember.objects.get_or_create(
        workspace=workspace,
        user=actor,
        defaults={
            "role": WorkspaceMember.Role.OWNER,
            "status": WorkspaceMember.Status.ACTIVE,
        },
    )
    return workspace


def list_user_workspaces(*, actor):
    if not actor or not actor.is_authenticated:
        return Workspace.objects.none()

    return Workspace.objects.filter(
        Q(owner=actor)
        | Q(
            memberships__user=actor,
            memberships__status=WorkspaceMember.Status.ACTIVE,
        )
    ).distinct()


def get_workspace_for_user(*, actor, workspace_slug: str) -> Workspace:
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    try:
        workspace = Workspace.objects.get(slug=workspace_slug)
    except Workspace.DoesNotExist as exc:
        raise PermissionDenied("Workspace not found.") from exc

    require_permission(actor=actor, workspace=workspace, permission=WORKSPACE_ACCESS)
    return workspace


def switch_active_workspace(*, actor, workspace: Workspace, session: dict) -> None:
    _ = get_workspace_for_user(actor=actor, workspace_slug=workspace.slug)
    session["active_workspace_slug"] = workspace.slug


def mark_workspace_onboarding_ready(*, workspace: Workspace, source: str, metadata: dict | None = None) -> Workspace:
    if workspace.onboarding_state == Workspace.OnboardingState.COMPLETED:
        return workspace

    merged_metadata = dict(workspace.onboarding_metadata or {})
    merged_metadata.update(metadata or {})
    merged_metadata["source"] = source

    workspace.onboarding_state = Workspace.OnboardingState.READY
    if workspace.onboarding_ready_at is None:
        workspace.onboarding_ready_at = timezone.now()
    workspace.onboarding_metadata = merged_metadata
    workspace.save(update_fields=["onboarding_state", "onboarding_ready_at", "onboarding_metadata", "updated_at"])
    return workspace


def complete_workspace_onboarding(*, workspace: Workspace, actor=None, metadata: dict | None = None) -> Workspace:
    merged_metadata = dict(workspace.onboarding_metadata or {})
    merged_metadata.update(metadata or {})
    merged_metadata["completed"] = True
    merged_metadata["completed_at"] = timezone.now().isoformat()

    workspace.onboarding_state = Workspace.OnboardingState.COMPLETED
    if workspace.onboarding_ready_at is None:
        workspace.onboarding_ready_at = timezone.now()
    workspace.onboarding_metadata = merged_metadata
    workspace.save(update_fields=["onboarding_state", "onboarding_ready_at", "onboarding_metadata", "updated_at"])

    log_action(
        actor=actor,
        workspace=workspace,
        action="workspace.onboarding.completed",
        target_type="workspace",
        target_id=workspace.id,
        metadata={
            "source": merged_metadata.get("source", "manual"),
            "completed": True,
        },
    )
    return workspace
