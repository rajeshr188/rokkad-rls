from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.verification import has_verified_email
from authorization.decorators import workspace_permission_required
from authorization.permissions import WORKSPACE_VIEW_DASHBOARD
from workspaces.services import complete_workspace_onboarding, create_workspace, list_user_workspaces


@login_required
def workspace_home_page(request):
	if not has_verified_email(actor=request.user):
		return redirect("account_email_verification_sent")

	workspaces = list_user_workspaces(actor=request.user)
	return render(
		request,
		"workspaces/home_page.html",
		{
			"workspaces": workspaces,
		},
	)


@login_required
def workspace_create_page(request):
	if not has_verified_email(actor=request.user):
		return redirect("account_email_verification_sent")

	if request.method == "POST":
		name = request.POST.get("name")
		try:
			workspace = create_workspace(actor=request.user, payload={"name": name})
			messages.success(request, "Workspace created successfully.")
			return redirect("workspaces:dashboard-page", workspace_slug=workspace.slug)
		except ValidationError as exc:
			messages.error(request, str(exc))

	return render(request, "workspaces/create_page.html")


@login_required
@workspace_permission_required(WORKSPACE_VIEW_DASHBOARD)
def workspace_dashboard(request, workspace_slug):
	workspace = request.active_workspace

	return JsonResponse(
		{
			"workspace": {
				"id": str(workspace.id),
				"name": workspace.name,
				"slug": workspace.slug,
			},
			"rls_context_applied": getattr(request, "rls_context_applied", False),
		}
	)


@login_required
@workspace_permission_required(WORKSPACE_VIEW_DASHBOARD)
def workspace_dashboard_page(request, workspace_slug):
	workspace = request.active_workspace
	return render(
		request,
		"workspaces/dashboard_page.html",
		{
			"workspace": workspace,
			"rls_context_applied": getattr(request, "rls_context_applied", False),
			"show_onboarding_prompt": workspace.onboarding_state == workspace.OnboardingState.READY,
		},
	)


@require_POST
@login_required
@workspace_permission_required(WORKSPACE_VIEW_DASHBOARD)
def workspace_complete_onboarding(request, workspace_slug):
	workspace = request.active_workspace
	complete_workspace_onboarding(
		workspace=workspace,
		actor=request.user,
		metadata={"source": "dashboard_action"},
	)
	messages.success(request, "Onboarding marked as complete.")
	return redirect("workspaces:dashboard-page", workspace_slug=workspace.slug)
