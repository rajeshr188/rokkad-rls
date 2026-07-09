from allauth.account.models import EmailAddress
from django.core.exceptions import PermissionDenied


def has_verified_email(*, actor) -> bool:
    if not actor or not actor.is_authenticated:
        return False

    return EmailAddress.objects.filter(user=actor, verified=True).exists()


def require_verified_email(*, actor) -> None:
    if has_verified_email(actor=actor):
        return
    raise PermissionDenied("Email verification is required.")
