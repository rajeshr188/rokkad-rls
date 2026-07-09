from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from authorization.decorators import workspace_permission_required
from authorization.permissions import BILLING_MANAGE, BILLING_VIEW
from authorization.policies import has_permission
from billing.services import (
	change_workspace_plan,
	create_checkout_session,
	ensure_workspace_subscription,
	get_public_plan_catalog,
	process_webhook_event,
	verify_webhook_signature,
)
from common.api import error_response, parse_json_body, validation_error_response
from workspaces.services import mark_workspace_onboarding_ready


@login_required
@workspace_permission_required(BILLING_VIEW)
def billing_page(request, workspace_slug):
	workspace = request.active_workspace
	subscription = ensure_workspace_subscription(workspace=workspace)
	can_manage_billing = has_permission(actor=request.user, workspace=workspace, permission=BILLING_MANAGE)

	if request.method == "POST":
		if not can_manage_billing:
			messages.error(request, "You do not have permission to manage billing.")
			return redirect("workspaces:billing:page", workspace_slug=workspace.slug)

		plan_code = request.POST.get("plan_code") or ""
		try:
			subscription = change_workspace_plan(workspace=workspace, plan_code=plan_code)
			messages.success(request, f"Plan changed to {subscription.plan.name}.")
		except ValidationError as exc:
			if hasattr(exc, "message_dict") and exc.message_dict.get("plan"):
				messages.error(request, exc.message_dict["plan"][0])
			else:
				messages.error(request, str(exc))

		return redirect("workspaces:billing:page", workspace_slug=workspace.slug)

	return render(
		request,
		"billing/billing_page.html",
		{
			"workspace": workspace,
			"subscription": subscription,
			"plans": get_public_plan_catalog(),
			"can_manage_billing": can_manage_billing,
			"is_subscription_restricted": subscription.state in {"past_due", "canceled", "expired"},
		},
	)


@login_required
@workspace_permission_required(BILLING_MANAGE)
def checkout_success_page(request, workspace_slug):
	workspace = request.active_workspace
	provider = (request.GET.get("provider") or "").strip() or None
	checkout_session_id = (request.GET.get("checkout_session_id") or "").strip() or None

	mark_workspace_onboarding_ready(
		workspace=workspace,
		source="checkout_callback",
		metadata={
			"provider": provider,
			"checkout_session_id": checkout_session_id,
		},
	)
	messages.success(request, "Checkout confirmed. Continue onboarding by inviting your team.")
	return redirect("workspaces:dashboard-page", workspace_slug=workspace.slug)


@require_POST
@login_required
@workspace_permission_required(BILLING_MANAGE)
def checkout_session_api(request, workspace_slug):
	workspace = request.active_workspace
	try:
		payload = parse_json_body(request)
		plan_code = payload.get("plan_code")
		if not plan_code:
			raise ValidationError({"plan": "Plan code is required."})

		default_return_url = request.build_absolute_uri(
			f"/w/{workspace.slug}/billing/ui/"
		)
		success_url = payload.get("success_url") or default_return_url
		cancel_url = payload.get("cancel_url") or default_return_url

		session = create_checkout_session(
			workspace=workspace,
			actor=request.user,
			plan_code=plan_code,
			success_url=success_url,
			cancel_url=cancel_url,
		)
		return JsonResponse({"data": session}, status=201)
	except ValidationError as exc:
		return validation_error_response(exc)


@csrf_exempt
@require_POST
def billing_webhook_api(request, provider):
	try:
		verify_webhook_signature(provider_name=provider, raw_body=request.body, headers=request.headers)
		payload = parse_json_body(request)
		result = process_webhook_event(provider_name=provider, payload=payload)
		return JsonResponse({"data": result}, status=200)
	except ValidationError as exc:
		status = 401 if hasattr(exc, "message_dict") and "signature" in exc.message_dict else 400
		return validation_error_response(exc, status=status)
	except Exception:
		return error_response(status=500, code="webhook_processing_failed", detail="Webhook processing failed.")
