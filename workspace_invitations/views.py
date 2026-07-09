from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render

from authorization.decorators import workspace_permission_required
from authorization.permissions import INVITATION_MANAGE, INVITATION_VIEW
from authorization.policies import has_permission
from common.api import error_response, parse_json_body, validation_error_response
from core.db import apply_invitation_token_context
from memberships.models import WorkspaceMember
from workspace_invitations.models import WorkspaceInvitation
from workspace_invitations.services import (
	accept_invitation,
	create_invitation,
	get_invitation,
	list_invitations,
	resend_invitation,
	revoke_invitation,
)


def _invitation_payload(invitation):
	return {
		"id": str(invitation.id),
		"workspace_id": str(invitation.workspace_id),
		"email": invitation.email,
		"role": invitation.role,
		"status": invitation.status,
		"expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
		"accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
		"revoked_at": invitation.revoked_at.isoformat() if invitation.revoked_at else None,
		"resend_count": invitation.resend_count,
	}


@login_required
@workspace_permission_required(INVITATION_VIEW)
def invitation_collection(request, workspace_slug):
	workspace = request.active_workspace

	if request.method == "GET":
		try:
			invitations = list_invitations(actor=request.user, workspace=workspace)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))

		return JsonResponse({"items": [_invitation_payload(invitation) for invitation in invitations]})

	if request.method == "POST":
		try:
			payload = parse_json_body(request)
			invitation = create_invitation(actor=request.user, workspace=workspace, payload=payload)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		except ValidationError as exc:
			return validation_error_response(exc)

		return JsonResponse(_invitation_payload(invitation), status=201)

	return error_response(status=405, code="method_not_allowed", detail="Allowed methods: GET, POST.")


@login_required
@workspace_permission_required(INVITATION_MANAGE)
def invitation_revoke(request, workspace_slug, invitation_id):
	workspace = request.active_workspace
	if request.method != "POST":
		return error_response(status=405, code="method_not_allowed", detail="Allowed methods: POST.")

	try:
		invitation = get_invitation(actor=request.user, workspace=workspace, invitation_id=invitation_id)
		invitation = revoke_invitation(actor=request.user, workspace=workspace, invitation=invitation)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		if "not found" in str(exc).lower():
			return validation_error_response(exc, code="not_found", status=404)
		return validation_error_response(exc)

	return JsonResponse(_invitation_payload(invitation))


@login_required
@workspace_permission_required(INVITATION_MANAGE)
def invitation_resend(request, workspace_slug, invitation_id):
	workspace = request.active_workspace
	if request.method != "POST":
		return error_response(status=405, code="method_not_allowed", detail="Allowed methods: POST.")

	try:
		invitation = get_invitation(actor=request.user, workspace=workspace, invitation_id=invitation_id)
		invitation = resend_invitation(actor=request.user, workspace=workspace, invitation=invitation)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		if "not found" in str(exc).lower():
			return validation_error_response(exc, code="not_found", status=404)
		return validation_error_response(exc)

	return JsonResponse(_invitation_payload(invitation))


@login_required
def invitation_accept(request, token):
	if request.method != "POST":
		return error_response(status=405, code="method_not_allowed", detail="Allowed methods: POST.")

	try:
		invitation, membership = accept_invitation(actor=request.user, token=token)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		if "invalid" in str(exc).lower() or "expired" in str(exc).lower() or "used" in str(exc).lower():
			return validation_error_response(exc, code="invalid_invitation", status=400)
		return validation_error_response(exc)

	return JsonResponse(
		{
			"invitation": _invitation_payload(invitation),
			"membership": {
				"id": str(membership.id),
				"workspace_id": str(membership.workspace_id),
				"user_id": membership.user_id,
				"role": membership.role,
				"status": membership.status,
			},
		}
	)


@login_required
@workspace_permission_required(INVITATION_VIEW)
def invitations_page(request, workspace_slug):
	workspace = request.active_workspace
	can_manage = has_permission(actor=request.user, workspace=workspace, permission=INVITATION_MANAGE)

	if request.method == "POST":
		if not can_manage:
			messages.error(request, "You do not have permission to manage invitations.")
			return redirect("workspaces:workspace_invitations:page", workspace_slug=workspace.slug)

		email = (request.POST.get("email") or "").strip()
		role = request.POST.get("role") or WorkspaceMember.Role.VIEWER
		try:
			create_invitation(actor=request.user, workspace=workspace, payload={"email": email, "role": role})
			messages.success(request, "Invitation created successfully.")
		except ValidationError as exc:
			messages.error(request, str(exc))

		return redirect("workspaces:workspace_invitations:page", workspace_slug=workspace.slug)

	invitations = list_invitations(actor=request.user, workspace=workspace)
	return render(
		request,
		"workspace_invitations/invitations_page.html",
		{
			"workspace": workspace,
			"invitations": invitations,
			"can_manage_invitations": can_manage,
			"role_choices": [choice for choice in WorkspaceMember.Role.choices if choice[0] != WorkspaceMember.Role.OWNER],
		},
	)


@login_required
@workspace_permission_required(INVITATION_MANAGE)
def invitation_revoke_page(request, workspace_slug, invitation_id):
	workspace = request.active_workspace
	if request.method != "POST":
		return HttpResponseNotAllowed(["POST"])

	try:
		invitation = get_invitation(actor=request.user, workspace=workspace, invitation_id=invitation_id)
		revoke_invitation(actor=request.user, workspace=workspace, invitation=invitation)
		messages.success(request, "Invitation revoked.")
	except ValidationError as exc:
		messages.error(request, str(exc))

	return redirect("workspaces:workspace_invitations:page", workspace_slug=workspace.slug)


@login_required
@workspace_permission_required(INVITATION_MANAGE)
def invitation_resend_page(request, workspace_slug, invitation_id):
	workspace = request.active_workspace
	if request.method != "POST":
		return HttpResponseNotAllowed(["POST"])

	try:
		invitation = get_invitation(actor=request.user, workspace=workspace, invitation_id=invitation_id)
		resend_invitation(actor=request.user, workspace=workspace, invitation=invitation)
		messages.success(request, "Invitation resent.")
	except ValidationError as exc:
		messages.error(request, str(exc))

	return redirect("workspaces:workspace_invitations:page", workspace_slug=workspace.slug)


@login_required
def invitation_accept_page(request, token):
	if request.method == "POST":
		try:
			invitation, _membership = accept_invitation(actor=request.user, token=token)
			messages.success(request, f"Invitation accepted for {invitation.workspace.name}.")
			return redirect("workspace-home")
		except PermissionDenied as exc:
			messages.error(request, str(exc))
		except ValidationError as exc:
			messages.error(request, str(exc))

	apply_invitation_token_context(token)
	invitation = WorkspaceInvitation.objects.filter(token=token).select_related("workspace").first()
	return render(
		request,
		"workspace_invitations/invitation_accept_page.html",
		{
			"invitation": invitation,
			"token": token,
		},
	)
