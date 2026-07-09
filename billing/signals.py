from django.db.models.signals import post_save
from django.dispatch import receiver

from billing.services import ensure_workspace_subscription
from workspaces.models import Workspace


@receiver(post_save, sender=Workspace)
def ensure_workspace_subscription_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    ensure_workspace_subscription(workspace=instance)
