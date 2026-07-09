from django.db.models.signals import post_save
from django.dispatch import receiver

from core.db import apply_workspace_context
from memberships.models import WorkspaceMember
from workspaces.models import Workspace


@receiver(post_save, sender=Workspace)
def ensure_owner_membership(sender, instance, created, **kwargs):
    if not created:
        return

    apply_workspace_context(instance.id)
    WorkspaceMember.objects.get_or_create(
        workspace=instance,
        user=instance.owner,
        defaults={
            "role": WorkspaceMember.Role.OWNER,
            "status": WorkspaceMember.Status.ACTIVE,
        },
    )
