from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render

from authorization.decorators import workspace_permission_required
from authorization.permissions import NOTES_CREATE, NOTES_DELETE, NOTES_VIEW
from authorization.policies import require_permission
from billing.decorators import workspace_feature_required
from billing.gates import FEATURE_NOTES_WRITE
from billing.gates import require_workspace_feature
from common.api import error_response, parse_json_body, validation_error_response
from notes.services import create_note, delete_note, get_note, list_notes, update_note


def _note_payload(note):
	return {
		"id": str(note.id),
		"title": note.title,
		"body": note.body,
		"workspace_id": str(note.workspace_id),
	}


@login_required
def notes_collection(request, workspace_slug):
	workspace = request.active_workspace

	if request.method == "GET":
		try:
			notes = list_notes(actor=request.user, workspace=workspace)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		return JsonResponse({"items": [_note_payload(note) for note in notes]})

	if request.method == "POST":
		try:
			require_workspace_feature(workspace=workspace, feature=FEATURE_NOTES_WRITE)
			require_permission(actor=request.user, workspace=workspace, permission=NOTES_CREATE)
			payload = parse_json_body(request)
			note = create_note(actor=request.user, workspace=workspace, payload=payload)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		except ValidationError as exc:
			return validation_error_response(exc)

		return JsonResponse(_note_payload(note), status=201)

	return error_response(status=405, code="method_not_allowed", detail="Allowed methods: GET, POST.")


@login_required
def note_detail(request, workspace_slug, note_id):
	workspace = request.active_workspace

	try:
		note = get_note(actor=request.user, workspace=workspace, note_id=note_id)
	except PermissionDenied as exc:
		return error_response(status=403, code="permission_denied", detail=str(exc))
	except ValidationError as exc:
		return validation_error_response(exc, code="not_found", status=404)

	if request.method == "GET":
		return JsonResponse(_note_payload(note))

	if request.method == "PATCH":
		try:
			require_workspace_feature(workspace=workspace, feature=FEATURE_NOTES_WRITE)
			payload = parse_json_body(request)
			note = update_note(actor=request.user, workspace=workspace, note=note, payload=payload)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		except ValidationError as exc:
			return validation_error_response(exc)
		return JsonResponse(_note_payload(note))

	if request.method == "DELETE":
		try:
			require_workspace_feature(workspace=workspace, feature=FEATURE_NOTES_WRITE)
			delete_note(actor=request.user, workspace=workspace, note=note)
		except PermissionDenied as exc:
			return error_response(status=403, code="permission_denied", detail=str(exc))
		return JsonResponse({}, status=204)

	return error_response(
		status=405,
		code="method_not_allowed",
		detail="Allowed methods: GET, PATCH, DELETE.",
	)


@login_required
@workspace_permission_required(NOTES_VIEW)
@workspace_feature_required(FEATURE_NOTES_WRITE, methods=["POST", "PATCH", "PUT", "DELETE"])
def notes_page(request, workspace_slug):
	workspace = request.active_workspace

	if request.method == "POST":
		require_permission(actor=request.user, workspace=workspace, permission=NOTES_CREATE)
		title = request.POST.get("title")
		body = request.POST.get("body")
		try:
			create_note(
				actor=request.user,
				workspace=workspace,
				payload={"title": title, "body": body},
			)
			messages.success(request, "Note created successfully.")
		except ValidationError as exc:
			messages.error(request, str(exc))

		return redirect("workspaces:notes:page", workspace_slug=workspace.slug)

	notes = list_notes(actor=request.user, workspace=workspace)
	return render(
		request,
		"notes/notes_page.html",
		{
			"workspace": workspace,
			"notes": notes,
		},
	)


@login_required
@workspace_permission_required(NOTES_DELETE)
@workspace_feature_required(FEATURE_NOTES_WRITE, methods=["POST", "PATCH", "PUT", "DELETE"])
def note_delete_page(request, workspace_slug, note_id):
	workspace = request.active_workspace

	if request.method != "POST":
		return HttpResponseNotAllowed(["POST"])

	try:
		note = get_note(actor=request.user, workspace=workspace, note_id=note_id)
		delete_note(actor=request.user, workspace=workspace, note=note)
		messages.success(request, "Note deleted.")
	except ValidationError as exc:
		messages.error(request, str(exc))

	return redirect("workspaces:notes:page", workspace_slug=workspace.slug)
