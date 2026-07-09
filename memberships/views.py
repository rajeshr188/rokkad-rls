from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render

from authorization.decorators import workspace_permission_required
from authorization.permissions import MEMBERSHIP_CHANGE_ROLE, MEMBERSHIP_MANAGE, MEMBERSHIP_VIEW
from authorization.policies import require_permission
from billing.decorators import workspace_feature_required
from billing.gates import FEATURE_MEMBERSHIPS_WRITE
from billing.gates import require_workspace_feature
from common.api import error_response, parse_json_body, validation_error_response
from memberships.models import WorkspaceMember
from memberships.services import add_member, change_member_role, get_member, list_members


User = get_user_model()


@login_required
def members_collection(request, workspace_slug):
	workspace = request.active_workspace

	if request.method == "GET":
		try:
			members = list_members(actor=request.user, workspace=workspace)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		return JsonResponse(
			{
				"items": [
					{
						"id": str(member.id),
						"user_id": member.user_id,
						"username": member.user.get_username(),
						"role": member.role,
						"status": member.status,
					}
					for member in members
				]
			}
		)

	if request.method == "POST":
		try:
			require_workspace_feature(workspace=workspace, feature=FEATURE_MEMBERSHIPS_WRITE)
			require_permission(actor=request.user, workspace=workspace, permission=MEMBERSHIP_MANAGE)
			payload = parse_json_body(request)

			user_id = payload.get("user_id")
			role = payload.get("role")
			if not user_id:
				return error_response(status=400, code="missing_field", detail="user_id is required.")

			target_user = User.objects.get(id=user_id)
			membership = add_member(
				actor=request.user,
				workspace=workspace,
				payload={"user": target_user, "role": role},
			)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		except User.DoesNotExist:
			return error_response(status=404, code="not_found", detail="User not found.")
		except ValidationError as exc:
			return validation_error_response(exc)

		return JsonResponse(
			{
				"id": str(membership.id),
				"user_id": membership.user_id,
				"role": membership.role,
				"status": membership.status,
			},
			status=201,
		)

	return error_response(status=405, code="method_not_allowed", detail="Allowed methods: GET, POST.")


@login_required
def member_role_update(request, workspace_slug, member_id):
	workspace = request.active_workspace

	if request.method != "PATCH":
		return error_response(status=405, code="method_not_allowed", detail="Allowed methods: PATCH.")

	try:
		require_workspace_feature(workspace=workspace, feature=FEATURE_MEMBERSHIPS_WRITE)
		require_permission(actor=request.user, workspace=workspace, permission=MEMBERSHIP_CHANGE_ROLE)
		payload = parse_json_body(request)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		return validation_error_response(exc)

	new_role = payload.get("role")
	if not new_role:
		return error_response(status=400, code="missing_field", detail="role is required.")

	try:
		member = get_member(actor=request.user, workspace=workspace, member_id=member_id)
		updated = change_member_role(
			actor=request.user,
			workspace=workspace,
			membership=member,
			new_role=new_role,
		)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		if "not found" in str(exc).lower():
			return validation_error_response(exc, code="not_found", status=404)
		return validation_error_response(exc)

	return JsonResponse(
		{
			"id": str(updated.id),
			"user_id": updated.user_id,
			"role": updated.role,
			"status": updated.status,
		}
	)


@login_required
@workspace_permission_required(MEMBERSHIP_VIEW)
@workspace_feature_required(FEATURE_MEMBERSHIPS_WRITE, methods=["POST", "PATCH", "PUT", "DELETE"])
def members_page(request, workspace_slug):
	workspace = request.active_workspace

	if request.method == "POST":
		require_permission(actor=request.user, workspace=workspace, permission=MEMBERSHIP_MANAGE)
		username = (request.POST.get("username") or "").strip()
		role = request.POST.get("role") or WorkspaceMember.Role.VIEWER

		try:
			target_user = User.objects.get(username=username)
			add_member(
				actor=request.user,
				workspace=workspace,
				payload={"user": target_user, "role": role},
			)
			messages.success(request, "Member added successfully.")
		except User.DoesNotExist:
			messages.error(request, "User not found.")
		except ValidationError as exc:
			messages.error(request, str(exc))

		return redirect("workspaces:memberships:page", workspace_slug=workspace.slug)

	members = list_members(actor=request.user, workspace=workspace)
	return render(
		request,
		"memberships/members_page.html",
		{
			"workspace": workspace,
			"members": members,
			"role_choices": WorkspaceMember.Role.choices,
		},
	)


@login_required
@workspace_permission_required(MEMBERSHIP_CHANGE_ROLE)
@workspace_feature_required(FEATURE_MEMBERSHIPS_WRITE, methods=["POST", "PATCH", "PUT", "DELETE"])
def member_role_update_page(request, workspace_slug, member_id):
	workspace = request.active_workspace

	if request.method != "POST":
		return HttpResponseNotAllowed(["POST"])

	new_role = request.POST.get("role")
	if not new_role:
		messages.error(request, "role is required.")
		return redirect("workspaces:memberships:page", workspace_slug=workspace.slug)

	try:
		member = get_member(actor=request.user, workspace=workspace, member_id=member_id)
		change_member_role(
			actor=request.user,
			workspace=workspace,
			membership=member,
			new_role=new_role,
		)
		messages.success(request, "Member role updated.")
	except ValidationError as exc:
		messages.error(request, str(exc))

	return redirect("workspaces:memberships:page", workspace_slug=workspace.slug)
