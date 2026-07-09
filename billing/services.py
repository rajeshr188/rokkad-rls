from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from billing.constants import FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE, PLAN_CATALOG
from billing.models import BillingWebhookEvent, Plan, Subscription, SubscriptionFeature
from billing.providers import MockBillingProvider, RazorpayBillingProvider, StripeBillingProvider
from core.db import apply_workspace_context


DEFAULT_PLAN_CODE = "starter"
DEFAULT_PLAN_NAME = "Starter"
DEFAULT_TRIAL_DAYS = 14
DEFAULT_BILLING_PROVIDER = "mock"


ALLOWED_STATE_TRANSITIONS = {
    Subscription.State.TRIALING: {
        Subscription.State.ACTIVE,
        Subscription.State.PAST_DUE,
        Subscription.State.CANCELED,
        Subscription.State.EXPIRED,
    },
    Subscription.State.ACTIVE: {
        Subscription.State.PAST_DUE,
        Subscription.State.CANCELED,
        Subscription.State.EXPIRED,
    },
    Subscription.State.PAST_DUE: {
        Subscription.State.ACTIVE,
        Subscription.State.CANCELED,
        Subscription.State.EXPIRED,
    },
    Subscription.State.CANCELED: {
        Subscription.State.EXPIRED,
        Subscription.State.ACTIVE,
    },
    Subscription.State.EXPIRED: {
        Subscription.State.ACTIVE,
    },
}


def get_or_create_default_plan() -> Plan:
    return ensure_plan_catalog()[DEFAULT_PLAN_CODE]


def ensure_plan_catalog() -> dict[str, Plan]:
    plans = {}
    for code, spec in PLAN_CATALOG.items():
        plan, _ = Plan.objects.get_or_create(
            code=code,
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "is_active": True,
            },
        )
        if plan.name != spec["name"] or plan.description != spec["description"]:
            plan.name = spec["name"]
            plan.description = spec["description"]
            plan.is_active = True
            plan.save(update_fields=["name", "description", "is_active", "updated_at"])

        configured_features = set(spec["features"])
        for feature_key in configured_features:
            SubscriptionFeature.objects.get_or_create(
                plan=plan,
                key=feature_key,
                defaults={"enabled": True},
            )
        SubscriptionFeature.objects.filter(plan=plan).exclude(key__in=configured_features).update(enabled=False)
        plans[code] = plan
    return plans


def get_public_plan_catalog():
    plans = ensure_plan_catalog()
    return [
        {
            "code": code,
            "name": plans[code].name,
            "description": PLAN_CATALOG[code]["description"],
            "monthly_price": PLAN_CATALOG[code]["monthly_price"],
            "features": PLAN_CATALOG[code]["features"],
        }
        for code in PLAN_CATALOG.keys()
    ]


def ensure_workspace_subscription(*, workspace, local=None) -> Subscription:
    apply_workspace_context(workspace.id, local=local)
    plan = get_or_create_default_plan()
    now = timezone.now()
    subscription, _ = Subscription.objects.get_or_create(
        workspace=workspace,
        defaults={
            "plan": plan,
            "state": Subscription.State.TRIALING,
            "trial_ends_at": now + timedelta(days=DEFAULT_TRIAL_DAYS),
            "current_period_start": now,
            "current_period_end": now + timedelta(days=DEFAULT_TRIAL_DAYS),
        },
    )
    return subscription


def get_workspace_subscription(*, workspace) -> Subscription | None:
    apply_workspace_context(workspace.id)
    return Subscription.objects.select_related("plan").filter(workspace=workspace).first()


def change_workspace_plan(*, workspace, plan_code: str) -> Subscription:
    apply_workspace_context(workspace.id)
    plans = ensure_plan_catalog()
    if plan_code not in plans:
        raise ValidationError({"plan": "Unknown plan."})

    subscription = ensure_workspace_subscription(workspace=workspace)
    subscription.plan = plans[plan_code]
    if subscription.state in {Subscription.State.CANCELED, Subscription.State.EXPIRED, Subscription.State.PAST_DUE}:
        subscription.state = Subscription.State.ACTIVE
    subscription.current_period_start = timezone.now()
    subscription.current_period_end = timezone.now() + timedelta(days=30)
    subscription.save(update_fields=["plan", "state", "current_period_start", "current_period_end", "updated_at"])
    return subscription


def transition_subscription_state(*, subscription: Subscription, new_state: str) -> Subscription:
    if new_state not in Subscription.State.values:
        raise ValidationError({"state": "Invalid subscription state."})

    current_state = subscription.state
    if new_state == current_state:
        return subscription

    allowed_next_states = ALLOWED_STATE_TRANSITIONS.get(current_state, set())
    if new_state not in allowed_next_states:
        raise ValidationError(f"Invalid transition from {current_state} to {new_state}.")

    with transaction.atomic():
        apply_workspace_context(subscription.workspace_id, local=True)
        subscription.state = new_state
        if new_state == Subscription.State.CANCELED:
            subscription.canceled_at = timezone.now()
        if new_state == Subscription.State.ACTIVE:
            subscription.canceled_at = None
            now = timezone.now()
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=30)
        if new_state == Subscription.State.EXPIRED and not subscription.current_period_end:
            subscription.current_period_end = timezone.now()
        subscription.save(update_fields=[
            "state",
            "canceled_at",
            "current_period_start",
            "current_period_end",
            "updated_at",
        ])

    return subscription


def get_billing_provider(*, provider_name: str | None = None):
    selected_provider = provider_name or getattr(settings, "BILLING_PROVIDER", DEFAULT_BILLING_PROVIDER)
    use_sdk = getattr(settings, "BILLING_USE_SDK", False)

    if selected_provider == MockBillingProvider.name:
        return MockBillingProvider()
    if selected_provider == StripeBillingProvider.name:
        return StripeBillingProvider(
            use_sdk=use_sdk,
            api_key=getattr(settings, "BILLING_STRIPE_SECRET_KEY", ""),
            webhook_secret=getattr(settings, "BILLING_WEBHOOK_SECRET_STRIPE", ""),
            price_lookup=getattr(settings, "BILLING_STRIPE_PRICE_LOOKUP", {}),
        )
    if selected_provider == RazorpayBillingProvider.name:
        return RazorpayBillingProvider(
            use_sdk=use_sdk,
            key_id=getattr(settings, "BILLING_RAZORPAY_KEY_ID", ""),
            key_secret=getattr(settings, "BILLING_RAZORPAY_KEY_SECRET", ""),
            webhook_secret=getattr(settings, "BILLING_WEBHOOK_SECRET_RAZORPAY", ""),
            plan_lookup=getattr(settings, "BILLING_RAZORPAY_PLAN_LOOKUP", {}),
        )
    raise ValidationError({"provider": f"Unsupported billing provider: {selected_provider}."})


def get_webhook_signature_header(*, provider_name: str) -> str | None:
    provider = get_billing_provider(provider_name=provider_name)
    return getattr(provider, "signature_header", None)


def verify_webhook_signature(*, provider_name: str, raw_body: bytes, headers: dict) -> None:
    provider = get_billing_provider(provider_name=provider_name)
    signature_header = getattr(provider, "signature_header", None)
    signature = headers.get(signature_header) if signature_header else None
    provider_secret_key = f"BILLING_WEBHOOK_SECRET_{provider_name.upper()}"
    secret = getattr(settings, provider_secret_key, "") or getattr(settings, "BILLING_WEBHOOK_SECRET", "")
    if not provider.verify_webhook_signature(raw_body=raw_body, signature=signature, secret=secret):
        raise ValidationError({"signature": "Invalid webhook signature."})


def create_checkout_session(
    *,
    workspace,
    actor,
    plan_code: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    plans = ensure_plan_catalog()
    if plan_code not in plans:
        raise ValidationError({"plan": "Unknown plan."})

    subscription = ensure_workspace_subscription(workspace=workspace)
    provider_name = subscription.provider or getattr(settings, "BILLING_PROVIDER", DEFAULT_BILLING_PROVIDER)
    provider = get_billing_provider(provider_name=provider_name)

    try:
        session = provider.create_checkout_session(
            workspace=workspace,
            actor=actor,
            plan_code=plan_code,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except (ImportError, ValueError) as exc:
        raise ValidationError({"provider": str(exc)}) from exc

    if not session.session_id:
        raise ValidationError({"provider": "Checkout session creation failed."})

    if subscription.provider != session.provider:
        subscription.provider = session.provider
        subscription.save(update_fields=["provider", "updated_at"])

    return {
        "provider": session.provider,
        "session_id": session.session_id,
        "checkout_url": session.checkout_url,
    }


def _apply_subscription_webhook_metadata(
    *,
    workspace,
    plan_code: str | None,
    state: str | None,
    local=None,
) -> Subscription:
    subscription = ensure_workspace_subscription(workspace=workspace, local=local)
    update_fields = []

    if plan_code:
        plans = ensure_plan_catalog()
        if plan_code not in plans:
            raise ValidationError({"plan": "Unknown plan from webhook payload."})
        subscription.plan = plans[plan_code]
        update_fields.append("plan")

    if state:
        if state not in Subscription.State.values:
            raise ValidationError({"state": "Unknown state from webhook payload."})
        subscription.state = state
        update_fields.append("state")
        if state == Subscription.State.CANCELED:
            subscription.canceled_at = timezone.now()
            update_fields.append("canceled_at")
        elif state == Subscription.State.ACTIVE:
            now = timezone.now()
            subscription.canceled_at = None
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=30)
            update_fields.extend(["canceled_at", "current_period_start", "current_period_end"])

    if update_fields:
        subscription.save(update_fields=[*update_fields, "updated_at"])

    return subscription


def _should_mark_onboarding_ready(*, event_type: str, state: str | None) -> bool:
    if event_type not in {"subscription.updated", "subscription.renewed", "subscription.created"}:
        return False
    return state in {None, Subscription.State.TRIALING, Subscription.State.ACTIVE}


def process_webhook_event(*, provider_name: str, payload: dict) -> dict:
    provider = get_billing_provider(provider_name=provider_name)
    normalized = provider.parse_webhook_event(payload=payload)
    event_id = normalized.get("id")
    if not event_id:
        raise ValidationError({"id": "Webhook payload is missing event id."})

    event_type = normalized.get("type", "")
    workspace_id = normalized.get("workspace_id")
    plan_code = normalized.get("plan_code")
    state = normalized.get("state")

    with transaction.atomic():
        webhook_event, created = BillingWebhookEvent.objects.select_for_update().get_or_create(
            provider=provider_name,
            event_id=str(event_id),
            defaults={
                "event_type": event_type,
                "payload": payload,
                "status": BillingWebhookEvent.Status.RECEIVED,
            },
        )

        if not created and webhook_event.status == BillingWebhookEvent.Status.PROCESSED:
            return {
                "status": "duplicate_ignored",
                "event_id": webhook_event.event_id,
                "provider": webhook_event.provider,
            }

        if not created:
            webhook_event.event_type = event_type
            webhook_event.payload = payload
            webhook_event.status = BillingWebhookEvent.Status.RECEIVED
            webhook_event.error_message = ""
            webhook_event.save(update_fields=["event_type", "payload", "status", "error_message", "updated_at"])

        try:
            from workspaces.models import Workspace

            if workspace_id:
                workspace = Workspace.objects.filter(id=workspace_id).first()
                if not workspace:
                    raise ValidationError({"workspace": "Unknown workspace in webhook payload."})
                apply_workspace_context(workspace.id, local=True)
                if event_type in {"subscription.updated", "subscription.renewed", "subscription.created"}:
                    _apply_subscription_webhook_metadata(
                        workspace=workspace,
                        plan_code=plan_code,
                        state=state,
                        local=True,
                    )
                if _should_mark_onboarding_ready(event_type=event_type, state=state):
                    from workspaces.services import mark_workspace_onboarding_ready

                    mark_workspace_onboarding_ready(
                        workspace=workspace,
                        source="webhook",
                        metadata={
                            "provider": provider_name,
                            "event_id": str(event_id),
                            "event_type": event_type,
                        },
                    )
        except ValidationError as exc:
            webhook_event.status = BillingWebhookEvent.Status.FAILED
            webhook_event.error_message = str(exc)
            webhook_event.save(update_fields=["status", "error_message", "updated_at"])
            raise

        webhook_event.status = BillingWebhookEvent.Status.PROCESSED
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at", "updated_at"])

    return {
        "status": "processed",
        "event_id": str(event_id),
        "provider": provider_name,
    }
