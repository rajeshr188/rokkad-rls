from django.core.exceptions import PermissionDenied

from billing.constants import FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE
from billing.models import SubscriptionFeature
from billing.services import ensure_workspace_subscription, get_workspace_subscription

FEATURE_ENABLED_SUBSCRIPTION_STATES = {"trialing", "active"}


def has_workspace_feature(*, workspace, feature: str) -> bool:
    subscription = get_workspace_subscription(workspace=workspace)
    if subscription is None:
        subscription = ensure_workspace_subscription(workspace=workspace)

    if subscription.state not in FEATURE_ENABLED_SUBSCRIPTION_STATES:
        return False

    feature_row = SubscriptionFeature.objects.filter(
        plan=subscription.plan,
        key=feature,
        enabled=True,
    ).first()
    return feature_row is not None


def require_workspace_feature(*, workspace, feature: str) -> None:
    if has_workspace_feature(workspace=workspace, feature=feature):
        return
    raise PermissionDenied(f"Your workspace subscription does not allow feature: {feature}.")
