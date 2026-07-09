from django.core.exceptions import ValidationError

from authorization.permissions import PARTY_CREATE, PARTY_DELETE, PARTY_UPDATE, PARTY_VIEW
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context
from party.models import Party


_ALLOWED_PARTY_TYPES = {choice for choice, _ in Party.PartyType.choices}


def _clean_list_field(payload: dict, field_name: str):
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValidationError({field_name: "Must be a list."})
    return value


def list_parties(*, actor, workspace):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_VIEW)
    apply_workspace_context(workspace.id)
    return Party.objects.filter(workspace=workspace)


def create_party(*, actor, workspace, payload: dict):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_CREATE)

    name = (payload.get("name") or "").strip()
    party_type = (payload.get("party_type") or "").strip().lower()
    if not name:
        raise ValidationError({"name": "Name is required."})
    if party_type not in _ALLOWED_PARTY_TYPES:
        raise ValidationError({"party_type": "Invalid party type."})

    roles = _clean_list_field(payload, "roles")
    contacts = _clean_list_field(payload, "contacts")
    addresses = _clean_list_field(payload, "addresses")
    documents = _clean_list_field(payload, "documents")

    apply_workspace_context(workspace.id)
    party = Party.objects.create(
        workspace=workspace,
        created_by=actor,
        name=name,
        party_type=party_type,
        roles=roles if roles is not None else [],
        contacts=contacts if contacts is not None else [],
        addresses=addresses if addresses is not None else [],
        documents=documents if documents is not None else [],
        is_active=bool(payload.get("is_active", True)),
    )
    log_action(
        actor=actor,
        workspace=workspace,
        action="party.created",
        target_type="Party",
        target_id=party.id,
        metadata={"name": party.name, "party_type": party.party_type},
    )
    return party


def get_party(*, actor, workspace, party_id):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_VIEW)
    apply_workspace_context(workspace.id)
    try:
        return Party.objects.get(workspace=workspace, id=party_id)
    except Party.DoesNotExist as exc:
        raise ValidationError("Party not found in workspace.") from exc


def update_party(*, actor, workspace, party, payload: dict):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_UPDATE)
    if party.workspace_id != workspace.id:
        raise ValidationError("Party does not belong to active workspace.")

    fields_to_update = ["updated_at"]

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Name cannot be blank."})
        party.name = name
        fields_to_update.append("name")

    if "party_type" in payload:
        party_type = (payload.get("party_type") or "").strip().lower()
        if party_type not in _ALLOWED_PARTY_TYPES:
            raise ValidationError({"party_type": "Invalid party type."})
        party.party_type = party_type
        fields_to_update.append("party_type")

    for list_field in ("roles", "contacts", "addresses", "documents"):
        if list_field in payload:
            value = _clean_list_field(payload, list_field)
            setattr(party, list_field, value)
            fields_to_update.append(list_field)

    if "is_active" in payload:
        party.is_active = bool(payload.get("is_active"))
        fields_to_update.append("is_active")

    apply_workspace_context(workspace.id)
    party.save(update_fields=fields_to_update)
    log_action(
        actor=actor,
        workspace=workspace,
        action="party.updated",
        target_type="Party",
        target_id=party.id,
        metadata={"updated_fields": sorted(set(fields_to_update) - {"updated_at"})},
    )
    return party


def delete_party(*, actor, workspace, party):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_DELETE)
    if party.workspace_id != workspace.id:
        raise ValidationError("Party does not belong to active workspace.")

    apply_workspace_context(workspace.id)
    party_id = party.id
    party_name = party.name
    party.delete()
    log_action(
        actor=actor,
        workspace=workspace,
        action="party.deleted",
        target_type="Party",
        target_id=party_id,
        metadata={"name": party_name},
    )
