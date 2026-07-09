import json
import hashlib
import hmac
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from allauth.account.models import EmailAddress

from billing.constants import FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE
from billing.gates import has_workspace_feature
from billing.models import BillingWebhookEvent, Plan, Subscription, SubscriptionFeature
from billing.services import ensure_workspace_subscription, transition_subscription_state
from memberships.services import add_member
from memberships.models import WorkspaceMember
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


def mock_signature(*, body: str, secret: str) -> str:
	return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def stripe_signature(*, body: str, secret: str, timestamp: str = "1700000000") -> str:
	signed_payload = f"{timestamp}.{body}"
	v1 = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
	return f"t={timestamp},v1={v1}"


def razorpay_signature(*, body: str, secret: str) -> str:
	return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


class BillingSubscriptionLifecycleTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="billing_owner", password="pass123")
		self.workspace = create_workspace(actor=self.owner, payload={"name": "Billing Space"})

	def test_workspace_creation_bootstraps_subscription_and_plan(self):
		subscription = Subscription.objects.filter(workspace=self.workspace).select_related("plan").first()

		self.assertIsNotNone(subscription)
		self.assertEqual(subscription.state, Subscription.State.TRIALING)
		self.assertEqual(subscription.plan.code, "starter")

		plan_features = set(
			SubscriptionFeature.objects.filter(plan=subscription.plan, enabled=True).values_list("key", flat=True)
		)
		self.assertIn(FEATURE_MEMBERSHIPS_WRITE, plan_features)
		self.assertIn(FEATURE_NOTES_WRITE, plan_features)

	def test_transition_subscription_state_enforces_state_machine(self):
		subscription = ensure_workspace_subscription(workspace=self.workspace)

		updated = transition_subscription_state(subscription=subscription, new_state=Subscription.State.ACTIVE)
		self.assertEqual(updated.state, Subscription.State.ACTIVE)

		updated = transition_subscription_state(subscription=subscription, new_state=Subscription.State.PAST_DUE)
		self.assertEqual(updated.state, Subscription.State.PAST_DUE)

		with self.assertRaises(ValidationError):
			transition_subscription_state(subscription=subscription, new_state=Subscription.State.TRIALING)

	@patch("billing.services.apply_workspace_context")
	def test_transition_subscription_state_uses_transaction_local_context(self, mock_apply_workspace_context):
		subscription = ensure_workspace_subscription(workspace=self.workspace)

		transition_subscription_state(subscription=subscription, new_state=Subscription.State.ACTIVE)

		mock_apply_workspace_context.assert_any_call(subscription.workspace_id, local=True)

	def test_feature_gate_uses_subscription_state_and_plan_features(self):
		subscription = ensure_workspace_subscription(workspace=self.workspace)
		self.assertTrue(has_workspace_feature(workspace=self.workspace, feature=FEATURE_NOTES_WRITE))

		transition_subscription_state(subscription=subscription, new_state=Subscription.State.CANCELED)
		self.assertFalse(has_workspace_feature(workspace=self.workspace, feature=FEATURE_NOTES_WRITE))

	def test_feature_gate_respects_disabled_feature_on_plan(self):
		subscription = ensure_workspace_subscription(workspace=self.workspace)
		feature = SubscriptionFeature.objects.get(plan=subscription.plan, key=FEATURE_MEMBERSHIPS_WRITE)
		feature.enabled = False
		feature.save(update_fields=["enabled", "updated_at"])

		self.assertFalse(has_workspace_feature(workspace=self.workspace, feature=FEATURE_MEMBERSHIPS_WRITE))


class BillingModelConstraintTests(TestCase):
	def test_plan_feature_key_unique_per_plan(self):
		plan = Plan.objects.create(code="pro", name="Pro")
		SubscriptionFeature.objects.create(plan=plan, key=FEATURE_NOTES_WRITE, enabled=True)

		with self.assertRaises(IntegrityError):
			SubscriptionFeature.objects.create(plan=plan, key=FEATURE_NOTES_WRITE, enabled=True)


class BillingProductSurfaceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="billing_ui_owner", password="pass123")
		self.admin = User.objects.create_user(username="billing_ui_admin", password="pass123")
		self.manager = User.objects.create_user(username="billing_ui_manager", password="pass123")
		self.unverified = User.objects.create_user(username="billing_ui_unverified", password="pass123")
		mark_verified(self.owner)
		mark_verified(self.admin)
		mark_verified(self.manager)
		self.workspace = create_workspace(actor=self.owner, payload={"name": "Billing UI Space"})
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.admin, "role": WorkspaceMember.Role.ADMIN},
		)
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.manager, "role": WorkspaceMember.Role.MANAGER},
		)

	def test_public_landing_page_renders(self):
		response = self.client.get(reverse("landing-page"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Workspace ERP infrastructure")

	def test_public_pricing_page_renders(self):
		response = self.client.get(reverse("pricing-page"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Pricing")
		self.assertContains(response, "Growth")

	def test_unverified_authenticated_user_sees_verify_cta_on_pricing_page(self):
		self.client.force_login(self.unverified)
		response = self.client.get(reverse("pricing-page"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Verify Email to Continue")

	def test_workspace_billing_page_renders_for_admin(self):
		self.client.force_login(self.admin)
		response = self.client.get(reverse("workspaces:billing:page", kwargs={"workspace_slug": self.workspace.slug}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Current Subscription")

	def test_workspace_billing_plan_change_updates_subscription(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:page", kwargs={"workspace_slug": self.workspace.slug}),
			data={"plan_code": "growth"},
		)
		self.assertEqual(response.status_code, 302)
		self.workspace.subscription.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, "growth")

	def test_workspace_billing_manager_cannot_change_plan(self):
		self.client.force_login(self.manager)
		current_plan_code = self.workspace.subscription.plan.code
		response = self.client.post(
			reverse("workspaces:billing:page", kwargs={"workspace_slug": self.workspace.slug}),
			data={"plan_code": "growth"},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.workspace.subscription.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, current_plan_code)
		self.assertContains(response, "You do not have permission to manage billing.")

	def test_workspace_billing_invalid_plan_shows_error(self):
		self.client.force_login(self.owner)
		current_plan_code = self.workspace.subscription.plan.code
		response = self.client.post(
			reverse("workspaces:billing:page", kwargs={"workspace_slug": self.workspace.slug}),
			data={"plan_code": "unknown-tier"},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.workspace.subscription.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, current_plan_code)
		self.assertContains(response, "Unknown plan.")

	def test_workspace_billing_shows_restricted_state_notice(self):
		subscription = ensure_workspace_subscription(workspace=self.workspace)
		transition_subscription_state(subscription=subscription, new_state=Subscription.State.CANCELED)

		self.client.force_login(self.owner)
		response = self.client.get(reverse("workspaces:billing:page", kwargs={"workspace_slug": self.workspace.slug}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Subscription status is canceled")

	def test_checkout_session_api_returns_session_for_owner(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertEqual(payload["data"]["provider"], "mock")
		self.assertIn("checkout_url", payload["data"])

	def test_checkout_session_api_requires_billing_manage_permission(self):
		self.client.force_login(self.manager)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 403)

	@override_settings(BILLING_PROVIDER="stripe")
	def test_checkout_session_api_uses_stripe_provider_when_configured(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertEqual(payload["data"]["provider"], "stripe")
		self.assertIn("checkout.stripe.com", payload["data"]["checkout_url"])

	@override_settings(
		BILLING_PROVIDER="stripe",
		BILLING_USE_SDK=True,
		BILLING_STRIPE_SECRET_KEY="sk_test_123",
		BILLING_STRIPE_PRICE_LOOKUP={"growth": "price_growth_123"},
	)
	@patch("billing.providers.importlib.import_module")
	def test_checkout_session_api_uses_stripe_sdk_when_enabled(self, mock_import_module):
		class _StripeCheckoutSession:
			@staticmethod
			def create(**kwargs):
				return {"id": "cs_live_123", "url": "https://checkout.stripe.com/c/pay/cs_live_123"}

		class _StripeCheckout:
			Session = _StripeCheckoutSession

		class _StripeModule:
			api_key = ""
			checkout = _StripeCheckout

		mock_import_module.return_value = _StripeModule

		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertEqual(payload["data"]["session_id"], "cs_live_123")
		self.assertEqual(payload["data"]["provider"], "stripe")

	@override_settings(BILLING_PROVIDER="stripe", BILLING_USE_SDK=True, BILLING_STRIPE_SECRET_KEY="")
	def test_checkout_session_api_returns_validation_error_when_stripe_sdk_config_missing(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	@override_settings(BILLING_PROVIDER="razorpay")
	def test_checkout_session_api_uses_razorpay_provider_when_configured(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertEqual(payload["data"]["provider"], "razorpay")
		self.assertIn("checkout.razorpay.com", payload["data"]["checkout_url"])

	@override_settings(
		BILLING_PROVIDER="razorpay",
		BILLING_USE_SDK=True,
		BILLING_RAZORPAY_KEY_ID="rzp_key",
		BILLING_RAZORPAY_KEY_SECRET="rzp_secret",
		BILLING_RAZORPAY_PLAN_LOOKUP={"growth": "plan_growth_123"},
	)
	@patch("billing.providers.importlib.import_module")
	def test_checkout_session_api_uses_razorpay_sdk_when_enabled(self, mock_import_module):
		class _SubscriptionLinkAPI:
			@staticmethod
			def create(data):
				return {"id": "sub_live_123", "short_url": "https://rzp.io/i/sub_live_123"}

		class _UtilityAPI:
			@staticmethod
			def verify_webhook_signature(payload, signature, secret):
				return True

		class _RazorpayClient:
			def __init__(self, auth):
				self.subscription_link = _SubscriptionLinkAPI()
				self.utility = _UtilityAPI()

		class _RazorpayModule:
			Client = _RazorpayClient

		mock_import_module.return_value = _RazorpayModule

		self.client.force_login(self.owner)
		response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": self.workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertEqual(payload["data"]["session_id"], "sub_live_123")
		self.assertEqual(payload["data"]["provider"], "razorpay")

	def test_checkout_success_callback_marks_workspace_onboarding_ready(self):
		self.client.force_login(self.owner)
		response = self.client.get(
			reverse("workspaces:billing:checkout-success-page", kwargs={"workspace_slug": self.workspace.slug}),
			data={"provider": "mock", "checkout_session_id": "mock_session_123"},
		)
		self.assertEqual(response.status_code, 302)
		self.workspace.refresh_from_db()
		self.assertEqual(self.workspace.onboarding_state, self.workspace.OnboardingState.READY)
		self.assertEqual(self.workspace.onboarding_metadata.get("source"), "checkout_callback")
		self.assertEqual(self.workspace.onboarding_metadata.get("provider"), "mock")
		self.assertEqual(self.workspace.onboarding_metadata.get("checkout_session_id"), "mock_session_123")


class BillingWebhookApiTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="billing_webhook_owner", password="pass123")
		mark_verified(self.owner)
		self.workspace = create_workspace(actor=self.owner, payload={"name": "Webhook Space"})

	def test_webhook_processes_subscription_update(self):
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps({
				"id": "evt_001",
				"type": "subscription.updated",
				"data": {
					"metadata": {
						"workspace_id": str(self.workspace.id),
						"plan_code": "growth",
						"state": "active",
					}
				},
			}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["data"]["status"], "processed")

		self.workspace.subscription.refresh_from_db()
		self.workspace.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, "growth")
		self.assertEqual(self.workspace.subscription.state, Subscription.State.ACTIVE)
		self.assertEqual(self.workspace.onboarding_state, self.workspace.OnboardingState.READY)

		event = BillingWebhookEvent.objects.get(provider="mock", event_id="evt_001")
		self.assertEqual(event.status, BillingWebhookEvent.Status.PROCESSED)

	@patch("billing.services._apply_subscription_webhook_metadata")
	def test_webhook_passes_local_context_to_subscription_update_helper(self, mock_apply_webhook_metadata):
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps(
				{
					"id": "evt_local_ctx_001",
					"type": "subscription.updated",
					"data": {
						"metadata": {
							"workspace_id": str(self.workspace.id),
							"plan_code": "starter",
							"state": "active",
						}
					},
				}
			),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(mock_apply_webhook_metadata.called)
		self.assertTrue(mock_apply_webhook_metadata.call_args.kwargs.get("local"))

	@patch("billing.services._apply_subscription_webhook_metadata")
	@patch("billing.services.apply_workspace_context")
	def test_webhook_applies_local_context_before_workspace_scoped_operations(
		self,
		mock_apply_workspace_context,
		mock_apply_webhook_metadata,
	):
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps(
				{
					"id": "evt_local_ctx_boundary_001",
					"type": "subscription.updated",
					"data": {
						"metadata": {
							"workspace_id": str(self.workspace.id),
							"plan_code": "starter",
							"state": "active",
						}
					},
				}
			),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		mock_apply_workspace_context.assert_any_call(self.workspace.id, local=True)

	def test_checkout_to_webhook_activation_flow_marks_onboarding_ready(self):
		owner = User.objects.create_user(username="billing_flow_owner", password="pass123")
		mark_verified(owner)
		workspace = create_workspace(actor=owner, payload={"name": "Flow Space"})

		self.client.force_login(owner)
		checkout_response = self.client.post(
			reverse("workspaces:billing:checkout-session-api", kwargs={"workspace_slug": workspace.slug}),
			data='{"plan_code": "growth"}',
			content_type="application/json",
		)
		self.assertEqual(checkout_response.status_code, 201)

		webhook_response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps(
				{
					"id": "evt_flow_001",
					"type": "subscription.updated",
					"data": {
						"metadata": {
							"workspace_id": str(workspace.id),
							"plan_code": "growth",
							"state": "active",
						}
					},
				}
			),
			content_type="application/json",
		)
		self.assertEqual(webhook_response.status_code, 200)

		workspace.refresh_from_db()
		self.assertEqual(workspace.onboarding_state, workspace.OnboardingState.READY)
		self.assertEqual(workspace.onboarding_metadata.get("source"), "webhook")

	def test_webhook_duplicate_event_is_idempotent(self):
		payload = {
			"id": "evt_duplicate",
			"type": "subscription.updated",
			"data": {
				"metadata": {
					"workspace_id": str(self.workspace.id),
					"plan_code": "starter",
					"state": "active",
				}
			},
		}
		first = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps(payload),
			content_type="application/json",
		)
		second = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps(payload),
			content_type="application/json",
		)

		self.assertEqual(first.status_code, 200)
		self.assertEqual(second.status_code, 200)
		self.assertEqual(second.json()["data"]["status"], "duplicate_ignored")
		self.assertEqual(
			BillingWebhookEvent.objects.filter(provider="mock", event_id="evt_duplicate").count(),
			1,
		)

	def test_webhook_missing_event_id_returns_validation_error(self):
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=json.dumps({"type": "subscription.updated", "data": {"metadata": {}}}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	@override_settings(BILLING_WEBHOOK_SECRET="test-secret")
	def test_webhook_with_valid_signature_is_accepted(self):
		body = json.dumps(
			{
				"id": "evt_sig_ok",
				"type": "subscription.updated",
				"data": {
					"metadata": {
						"workspace_id": str(self.workspace.id),
						"plan_code": "starter",
						"state": "active",
					}
				},
			}
		)
		signature = mock_signature(body=body, secret="test-secret")
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=body,
			content_type="application/json",
			HTTP_X_MOCK_SIGNATURE=signature,
		)
		self.assertEqual(response.status_code, 200)

	@override_settings(BILLING_WEBHOOK_SECRET="test-secret")
	def test_webhook_with_missing_signature_is_rejected(self):
		body = json.dumps(
			{
				"id": "evt_sig_missing",
				"type": "subscription.updated",
				"data": {"metadata": {"workspace_id": str(self.workspace.id)}},
			}
		)
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=body,
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	@override_settings(BILLING_WEBHOOK_SECRET="test-secret")
	def test_webhook_with_invalid_signature_is_rejected(self):
		body = json.dumps(
			{
				"id": "evt_sig_bad",
				"type": "subscription.updated",
				"data": {"metadata": {"workspace_id": str(self.workspace.id)}},
			}
		)
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "mock"}),
			data=body,
			content_type="application/json",
			HTTP_X_MOCK_SIGNATURE="bad-signature",
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	@override_settings(BILLING_WEBHOOK_SECRET_STRIPE="stripe-secret")
	def test_stripe_webhook_with_valid_signature_is_processed(self):
		body = json.dumps(
			{
				"id": "evt_stripe_001",
				"type": "customer.subscription.updated",
				"data": {
					"object": {
						"status": "active",
						"metadata": {
							"workspace_id": str(self.workspace.id),
							"plan_code": "growth",
						},
					}
				},
			}
		)
		signature = stripe_signature(body=body, secret="stripe-secret")
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "stripe"}),
			data=body,
			content_type="application/json",
			HTTP_STRIPE_SIGNATURE=signature,
		)
		self.assertEqual(response.status_code, 200)
		self.workspace.subscription.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, "growth")
		self.assertEqual(self.workspace.subscription.state, Subscription.State.ACTIVE)
		event = BillingWebhookEvent.objects.get(provider="stripe", event_id="evt_stripe_001")
		self.assertEqual(event.status, BillingWebhookEvent.Status.PROCESSED)

	@override_settings(BILLING_WEBHOOK_SECRET_STRIPE="stripe-secret")
	def test_stripe_webhook_with_invalid_signature_is_rejected(self):
		body = json.dumps(
			{
				"id": "evt_stripe_bad",
				"type": "customer.subscription.updated",
				"data": {
					"object": {
						"status": "active",
						"metadata": {"workspace_id": str(self.workspace.id)},
					}
				},
			}
		)
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "stripe"}),
			data=body,
			content_type="application/json",
			HTTP_STRIPE_SIGNATURE="t=1700000000,v1=bad",
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	@override_settings(BILLING_WEBHOOK_SECRET_RAZORPAY="rzp-secret")
	def test_razorpay_webhook_with_valid_signature_is_processed(self):
		body = json.dumps(
			{
				"event": "subscription.activated",
				"payload": {
					"subscription": {
						"entity": {
							"id": "sub_rzp_001",
							"status": "active",
							"notes": {
								"workspace_id": str(self.workspace.id),
								"plan_code": "growth",
							},
						}
					}
				},
			}
		)
		signature = razorpay_signature(body=body, secret="rzp-secret")
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "razorpay"}),
			data=body,
			content_type="application/json",
			HTTP_X_RAZORPAY_SIGNATURE=signature,
		)
		self.assertEqual(response.status_code, 200)
		self.workspace.subscription.refresh_from_db()
		self.assertEqual(self.workspace.subscription.plan.code, "growth")
		self.assertEqual(self.workspace.subscription.state, Subscription.State.ACTIVE)
		event = BillingWebhookEvent.objects.get(provider="razorpay", event_id="sub_rzp_001")
		self.assertEqual(event.status, BillingWebhookEvent.Status.PROCESSED)

	@override_settings(BILLING_WEBHOOK_SECRET_RAZORPAY="rzp-secret")
	def test_razorpay_webhook_with_invalid_signature_is_rejected(self):
		body = json.dumps(
			{
				"event": "subscription.activated",
				"payload": {
					"subscription": {
						"entity": {
							"id": "sub_rzp_bad",
							"status": "active",
							"notes": {"workspace_id": str(self.workspace.id)},
						}
					}
				},
			}
		)
		response = self.client.post(
			reverse("billing-webhook-api", kwargs={"provider": "razorpay"}),
			data=body,
			content_type="application/json",
			HTTP_X_RAZORPAY_SIGNATURE="bad-signature",
		)
		self.assertEqual(response.status_code, 401)
		self.assertEqual(response.json()["error"]["code"], "validation_error")
