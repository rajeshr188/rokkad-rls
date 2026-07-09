from django.core.exceptions import ValidationError

from authorization.permissions import NOTES_CREATE, NOTES_DELETE, NOTES_UPDATE, NOTES_VIEW
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context
from notes.models import Note


def list_notes(*, actor, workspace):
    require_permission(actor=actor, workspace=workspace, permission=NOTES_VIEW)
    apply_workspace_context(workspace.id)
    return Note.objects.filter(workspace=workspace)


def create_note(*, actor, workspace, payload: dict):
    require_permission(actor=actor, workspace=workspace, permission=NOTES_CREATE)

    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title:
        raise ValidationError({"title": "Title is required."})

    apply_workspace_context(workspace.id)
    note = Note.objects.create(
        workspace=workspace,
        created_by=actor,
        title=title,
        body=body,
    )
    log_action(
        actor=actor,
        workspace=workspace,
        action="note.created",
        target_type="Note",
        target_id=note.id,
        metadata={"title": note.title},
    )
    return note


def get_note(*, actor, workspace, note_id):
    require_permission(actor=actor, workspace=workspace, permission=NOTES_VIEW)
    apply_workspace_context(workspace.id)
    try:
        return Note.objects.get(workspace=workspace, id=note_id)
    except Note.DoesNotExist as exc:
        raise ValidationError("Note not found in workspace.") from exc


def update_note(*, actor, workspace, note, payload: dict):
    require_permission(actor=actor, workspace=workspace, permission=NOTES_UPDATE)
    if note.workspace_id != workspace.id:
        raise ValidationError("Note does not belong to active workspace.")

    title = payload.get("title")
    body = payload.get("body")
    previous_title = note.title
    previous_body = note.body
    if title is not None:
        title = title.strip()
        if not title:
            raise ValidationError({"title": "Title cannot be blank."})
        note.title = title
    if body is not None:
        note.body = body.strip()

    apply_workspace_context(workspace.id)
    note.save(update_fields=["title", "body", "updated_at"])
    log_action(
        actor=actor,
        workspace=workspace,
        action="note.updated",
        target_type="Note",
        target_id=note.id,
        metadata={
            "previous_title": previous_title,
            "new_title": note.title,
            "body_changed": previous_body != note.body,
        },
    )
    return note


def delete_note(*, actor, workspace, note):
    require_permission(actor=actor, workspace=workspace, permission=NOTES_DELETE)
    if note.workspace_id != workspace.id:
        raise ValidationError("Note does not belong to active workspace.")

    apply_workspace_context(workspace.id)
    note_id = note.id
    note_title = note.title
    note.delete()
    log_action(
        actor=actor,
        workspace=workspace,
        action="note.deleted",
        target_type="Note",
        target_id=note_id,
        metadata={"title": note_title},
    )
