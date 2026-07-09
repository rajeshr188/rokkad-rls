import hashlib
import hmac
import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutSession:
    provider: str
    session_id: str
    checkout_url: str


class MockBillingProvider:
    name = "mock"
    signature_header = "X-Mock-Signature"

    def create_checkout_session(
        self,
        *,
        workspace,
        actor,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        session_id = f"mock_{workspace.id}_{plan_code}"
        checkout_url = f"{success_url}?checkout_session_id={session_id}&plan={plan_code}"
        return CheckoutSession(provider=self.name, session_id=session_id, checkout_url=checkout_url)

    def parse_webhook_event(self, *, payload: dict) -> dict:
        event_id = payload.get("id")
        event_type = payload.get("type", "")
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        metadata = data.get("metadata", {}) if isinstance(data, dict) else {}

        return {
            "id": event_id,
            "type": event_type,
            "workspace_id": metadata.get("workspace_id"),
            "plan_code": metadata.get("plan_code"),
            "state": metadata.get("state"),
        }

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None, secret: str | None) -> bool:
        # Allow local development without signature enforcement when no secret is configured.
        if not secret:
            return True
        if not signature:
            return False

        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


class StripeBillingProvider:
    name = "stripe"
    signature_header = "Stripe-Signature"

    def __init__(
        self,
        *,
        use_sdk: bool = False,
        api_key: str = "",
        webhook_secret: str = "",
        price_lookup: dict[str, str] | None = None,
    ):
        self.use_sdk = use_sdk
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.price_lookup = price_lookup or {}

    _EVENT_TYPE_MAP = {
        "customer.subscription.created": "subscription.created",
        "customer.subscription.updated": "subscription.updated",
        "customer.subscription.deleted": "subscription.deleted",
    }

    _STATUS_MAP = {
        "trialing": "trialing",
        "active": "active",
        "past_due": "past_due",
        "canceled": "canceled",
        "unpaid": "past_due",
        "incomplete_expired": "expired",
    }

    def create_checkout_session(
        self,
        *,
        workspace,
        actor,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        if self.use_sdk:
            stripe = importlib.import_module("stripe")
            if not self.api_key:
                raise ValueError("Stripe SDK mode requires BILLING_STRIPE_SECRET_KEY.")

            price_id = self.price_lookup.get(plan_code)
            if not price_id:
                raise ValueError("Stripe SDK mode requires BILLING_STRIPE_PRICE_LOOKUP for the selected plan.")

            stripe.api_key = self.api_key
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=str(workspace.id),
                metadata={
                    "workspace_id": str(workspace.id),
                    "plan_code": plan_code,
                    "actor_id": str(actor.id),
                },
            )
            return CheckoutSession(
                provider=self.name,
                session_id=session["id"],
                checkout_url=session.get("url") or success_url,
            )

        session_id = f"cs_test_{workspace.id.hex[:12]}_{plan_code}"
        checkout_url = f"https://checkout.stripe.com/c/pay/{session_id}?success_url={success_url}&cancel_url={cancel_url}"
        return CheckoutSession(provider=self.name, session_id=session_id, checkout_url=checkout_url)

    def parse_webhook_event(self, *, payload: dict) -> dict:
        event_id = payload.get("id")
        incoming_type = payload.get("type", "")
        normalized_type = self._EVENT_TYPE_MAP.get(incoming_type, incoming_type)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        obj = data.get("object", {}) if isinstance(data, dict) else {}
        metadata = obj.get("metadata", {}) if isinstance(obj, dict) else {}
        raw_status = obj.get("status")

        return {
            "id": event_id,
            "type": normalized_type,
            "workspace_id": metadata.get("workspace_id"),
            "plan_code": metadata.get("plan_code"),
            "state": self._STATUS_MAP.get(raw_status, raw_status),
        }

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None, secret: str | None) -> bool:
        if self.use_sdk:
            if not signature:
                return False
            try:
                stripe = importlib.import_module("stripe")
                stripe.Webhook.construct_event(
                    payload=raw_body.decode("utf-8"),
                    sig_header=signature,
                    secret=secret or self.webhook_secret,
                )
                return True
            except Exception:
                return False

        if not secret:
            return True
        if not signature:
            return False

        fields = {}
        for part in signature.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()

        timestamp = fields.get("t")
        signed_v1 = fields.get("v1")
        if not timestamp or not signed_v1:
            return False

        try:
            payload_to_sign = f"{timestamp}.{raw_body.decode('utf-8')}"
        except UnicodeDecodeError:
            return False

        expected = hmac.new(secret.encode("utf-8"), payload_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signed_v1, expected)


class RazorpayBillingProvider:
    name = "razorpay"
    signature_header = "X-Razorpay-Signature"

    def __init__(
        self,
        *,
        use_sdk: bool = False,
        key_id: str = "",
        key_secret: str = "",
        webhook_secret: str = "",
        plan_lookup: dict[str, str] | None = None,
    ):
        self.use_sdk = use_sdk
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.plan_lookup = plan_lookup or {}

    _EVENT_TYPE_MAP = {
        "subscription.authenticated": "subscription.created",
        "subscription.activated": "subscription.updated",
        "subscription.charged": "subscription.updated",
        "subscription.cancelled": "subscription.updated",
        "subscription.halted": "subscription.updated",
    }

    _STATUS_MAP = {
        "created": "trialing",
        "authenticated": "trialing",
        "active": "active",
        "pending": "past_due",
        "halted": "past_due",
        "cancelled": "canceled",
        "completed": "expired",
    }

    def create_checkout_session(
        self,
        *,
        workspace,
        actor,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        if self.use_sdk:
            razorpay = importlib.import_module("razorpay")
            if not self.key_id or not self.key_secret:
                raise ValueError("Razorpay SDK mode requires BILLING_RAZORPAY_KEY_ID and BILLING_RAZORPAY_KEY_SECRET.")

            plan_id = self.plan_lookup.get(plan_code)
            if not plan_id:
                raise ValueError("Razorpay SDK mode requires BILLING_RAZORPAY_PLAN_LOOKUP for the selected plan.")

            client = razorpay.Client(auth=(self.key_id, self.key_secret))
            checkout = client.subscription_link.create(
                data={
                    "plan_id": plan_id,
                    "total_count": 12,
                    "customer_notify": 1,
                    "notes": {
                        "workspace_id": str(workspace.id),
                        "plan_code": plan_code,
                        "actor_id": str(actor.id),
                    },
                    "callback_url": success_url,
                    "callback_method": "get",
                }
            )

            return CheckoutSession(
                provider=self.name,
                session_id=checkout.get("id", f"rzp_sub_{workspace.id.hex[:12]}_{plan_code}"),
                checkout_url=checkout.get("short_url") or success_url,
            )

        session_id = f"rzp_sub_{workspace.id.hex[:12]}_{plan_code}"
        checkout_url = f"https://checkout.razorpay.com/v1/checkout.js?subscription_id={session_id}&callback_url={success_url}"
        return CheckoutSession(provider=self.name, session_id=session_id, checkout_url=checkout_url)

    def parse_webhook_event(self, *, payload: dict) -> dict:
        event_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("id") or payload.get("id")
        incoming_type = payload.get("event", "")
        normalized_type = self._EVENT_TYPE_MAP.get(incoming_type, incoming_type)

        subscription_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        notes = subscription_entity.get("notes", {}) if isinstance(subscription_entity, dict) else {}
        raw_status = subscription_entity.get("status") if isinstance(subscription_entity, dict) else None

        return {
            "id": event_id,
            "type": normalized_type,
            "workspace_id": notes.get("workspace_id"),
            "plan_code": notes.get("plan_code"),
            "state": self._STATUS_MAP.get(raw_status, raw_status),
        }

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None, secret: str | None) -> bool:
        if self.use_sdk:
            if not signature:
                return False
            try:
                razorpay = importlib.import_module("razorpay")
                client = razorpay.Client(auth=(self.key_id, self.key_secret))
                client.utility.verify_webhook_signature(
                    raw_body.decode("utf-8"),
                    signature,
                    secret or self.webhook_secret,
                )
                return True
            except Exception:
                return False

        if not secret:
            return True
        if not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
