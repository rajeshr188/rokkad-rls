from django.core.exceptions import ValidationError
from django.db import transaction

from authorization.permissions import PARTY_CREATE, PARTY_DELETE, PARTY_UPDATE, PARTY_VIEW
from authorization.policies import require_permission
from common.audit import log_action
from core.db import apply_workspace_context
from party.models import (
    Party,
    PartyAddress,
    PartyContactMethod,
    PartyDocument,
    PartyRole,
    PartyRoleType,
)


_ALLOWED_PARTY_TYPES = {choice for choice, _ in Party.PartyType.choices}
_ALLOWED_CONTACT_TYPES = {choice for choice, _ in PartyContactMethod.ContactType.choices}
_ALLOWED_ADDRESS_TYPES = {choice for choice, _ in PartyAddress.AddressType.choices}
_ALLOWED_DOCUMENT_TYPES = {choice for choice, _ in PartyDocument.DocumentType.choices}
_DOCUMENT_TYPE_ALIASES = {
    "gst": PartyDocument.DocumentType.TAX,
    "pan": PartyDocument.DocumentType.TAX,
    "aadhaar": PartyDocument.DocumentType.KYC,
    "aadhar": PartyDocument.DocumentType.KYC,
}


def _clean_list_field(payload: dict, field_name: str):
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValidationError({field_name: "Must be a list."})
    return value


def _ensure_role_type(*, role_key: str):
    key = (role_key or "").strip().upper()
    if not key:
        raise ValidationError({"roles": "Role key cannot be blank."})

    role_type, _ = PartyRoleType.objects.get_or_create(
        key=key,
        defaults={
            "label": key.replace("_", " ").title(),
            "is_system": False,
            "is_active": True,
        },
    )
    return role_type


def _apply_roles(*, party, workspace, actor, roles):
    PartyRole.objects.filter(workspace=workspace, party=party).delete()
    for item in roles or []:
        if isinstance(item, str):
            role_key = item
            segment = ""
            status = PartyRole.Status.ACTIVE
            metadata = {}
        elif isinstance(item, dict):
            role_key = item.get("key") or item.get("role") or item.get("role_type") or ""
            segment = (item.get("segment") or "").strip()
            status = (item.get("status") or PartyRole.Status.ACTIVE).strip().lower()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        else:
            raise ValidationError({"roles": "Each role must be a string or object."})

        if status not in {choice for choice, _ in PartyRole.Status.choices}:
            raise ValidationError({"roles": f"Invalid role status: {status}"})

        role_type = _ensure_role_type(role_key=role_key)
        PartyRole.objects.create(
            workspace=workspace,
            created_by=actor,
            party=party,
            role_type=role_type,
            status=status,
            segment=segment,
            metadata=metadata,
        )


def _infer_contact_type(value: str):
    text = (value or "").strip()
    lower = text.lower()
    if "@" in lower:
        return PartyContactMethod.ContactType.EMAIL
    if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("www."):
        return PartyContactMethod.ContactType.WEBSITE
    return PartyContactMethod.ContactType.PHONE


def _apply_contacts(*, party, workspace, actor, contacts):
    PartyContactMethod.objects.filter(workspace=workspace, party=party).delete()
    for item in contacts or []:
        if not isinstance(item, dict):
            raise ValidationError({"contacts": "Each contact must be an object."})

        value = (item.get("value") or item.get("phone") or item.get("email") or "").strip()
        if not value:
            raise ValidationError({"contacts": "Each contact requires value/phone/email."})

        contact_type = (item.get("contact_type") or _infer_contact_type(value)).strip().lower()
        if contact_type not in _ALLOWED_CONTACT_TYPES:
            raise ValidationError({"contacts": f"Invalid contact type: {contact_type}"})

        PartyContactMethod.objects.create(
            workspace=workspace,
            created_by=actor,
            party=party,
            contact_type=contact_type,
            label=(item.get("label") or item.get("name") or "").strip(),
            value=value,
            normalized_value=(item.get("normalized_value") or value).strip().lower(),
            is_primary=bool(item.get("is_primary", False)),
            is_verified=bool(item.get("is_verified", False)),
        )


def _apply_addresses(*, party, workspace, actor, addresses):
    PartyAddress.objects.filter(workspace=workspace, party=party).delete()
    for item in addresses or []:
        if not isinstance(item, dict):
            raise ValidationError({"addresses": "Each address must be an object."})

        line1 = (item.get("line1") or "").strip()
        city = (item.get("city") or "").strip()
        if not line1 or not city:
            raise ValidationError({"addresses": "Each address requires line1 and city."})

        address_type = (item.get("address_type") or PartyAddress.AddressType.OTHER).strip().lower()
        if address_type not in _ALLOWED_ADDRESS_TYPES:
            raise ValidationError({"addresses": f"Invalid address type: {address_type}"})

        PartyAddress.objects.create(
            workspace=workspace,
            created_by=actor,
            party=party,
            address_type=address_type,
            line1=line1,
            line2=(item.get("line2") or "").strip(),
            area=(item.get("area") or "").strip(),
            city=city,
            state=(item.get("state") or "").strip(),
            postal_code=(item.get("postal_code") or item.get("zip") or "").strip(),
            country=(item.get("country") or "IN").strip().upper(),
            is_default=bool(item.get("is_default", False)),
            is_verified=bool(item.get("is_verified", False)),
        )


def _apply_documents(*, party, workspace, actor, documents):
    PartyDocument.objects.filter(workspace=workspace, party=party).delete()
    for item in documents or []:
        if not isinstance(item, dict):
            raise ValidationError({"documents": "Each document must be an object."})

        raw_document_type = (item.get("document_type") or item.get("type") or PartyDocument.DocumentType.OTHER).strip().lower()
        document_type = _DOCUMENT_TYPE_ALIASES.get(raw_document_type, raw_document_type)
        if document_type not in _ALLOWED_DOCUMENT_TYPES:
            raise ValidationError({"documents": f"Invalid document type: {document_type}"})

        title = (item.get("title") or item.get("name") or document_type.upper()).strip()
        if not title:
            raise ValidationError({"documents": "Each document requires title or type."})

        PartyDocument.objects.create(
            workspace=workspace,
            created_by=actor,
            party=party,
            document_type=document_type,
            title=title,
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            is_verified=bool(item.get("is_verified", False)),
        )


def _sync_denormalized_contact_fields(*, party, workspace):
    primary_phone = ""
    primary_email = ""

    phone = (
        PartyContactMethod.objects.filter(
            workspace=workspace,
            party=party,
            contact_type__in=[
                PartyContactMethod.ContactType.PHONE,
                PartyContactMethod.ContactType.MOBILE,
                PartyContactMethod.ContactType.WHATSAPP,
            ],
            is_primary=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if phone:
        primary_phone = phone.value

    email = (
        PartyContactMethod.objects.filter(
            workspace=workspace,
            party=party,
            contact_type=PartyContactMethod.ContactType.EMAIL,
            is_primary=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if email:
        primary_email = email.value

    party.primary_phone = primary_phone
    party.primary_email = primary_email


def list_parties(*, actor, workspace):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_VIEW)
    apply_workspace_context(workspace.id)
    return Party.objects.filter(workspace=workspace).prefetch_related(
        "party_roles__role_type",
        "contact_methods",
        "party_addresses",
        "party_documents",
    )


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
    with transaction.atomic():
        party = Party.objects.create(
            workspace=workspace,
            created_by=actor,
            updated_by=actor,
            name=name,
            display_name=(payload.get("display_name") or name).strip(),
            legal_name=(payload.get("legal_name") or "").strip(),
            party_type=party_type,
            roles=roles if roles is not None else [],
            contacts=contacts if contacts is not None else [],
            addresses=addresses if addresses is not None else [],
            documents=documents if documents is not None else [],
            is_active=bool(payload.get("is_active", True)),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )

        _apply_roles(party=party, workspace=workspace, actor=actor, roles=party.roles)
        _apply_contacts(party=party, workspace=workspace, actor=actor, contacts=party.contacts)
        _apply_addresses(party=party, workspace=workspace, actor=actor, addresses=party.addresses)
        _apply_documents(party=party, workspace=workspace, actor=actor, documents=party.documents)
        _sync_denormalized_contact_fields(party=party, workspace=workspace)
        party.save(update_fields=["primary_phone", "primary_email", "updated_at"])
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
        return Party.objects.prefetch_related(
            "party_roles__role_type",
            "contact_methods",
            "party_addresses",
            "party_documents",
        ).get(workspace=workspace, id=party_id)
    except Party.DoesNotExist as exc:
        raise ValidationError("Party not found in workspace.") from exc


def update_party(*, actor, workspace, party, payload: dict):
    require_permission(actor=actor, workspace=workspace, permission=PARTY_UPDATE)
    if party.workspace_id != workspace.id:
        raise ValidationError("Party does not belong to active workspace.")

    fields_to_update = ["updated_at", "updated_by"]
    normalized_refresh_required = False

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Name cannot be blank."})
        party.name = name
        party.display_name = name
        fields_to_update.append("name")
        fields_to_update.append("display_name")

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
            normalized_refresh_required = True

    if "is_active" in payload:
        party.is_active = bool(payload.get("is_active"))
        fields_to_update.append("is_active")

    if "display_name" in payload:
        party.display_name = (payload.get("display_name") or "").strip()
        if not party.display_name:
            raise ValidationError({"display_name": "Display name cannot be blank."})
        fields_to_update.append("display_name")

    if "legal_name" in payload:
        party.legal_name = (payload.get("legal_name") or "").strip()
        fields_to_update.append("legal_name")

    if "metadata" in payload:
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValidationError({"metadata": "Must be an object."})
        party.metadata = metadata or {}
        fields_to_update.append("metadata")

    party.updated_by = actor

    apply_workspace_context(workspace.id)
    with transaction.atomic():
        party.save(update_fields=fields_to_update)
        if normalized_refresh_required:
            _apply_roles(party=party, workspace=workspace, actor=actor, roles=party.roles)
            _apply_contacts(party=party, workspace=workspace, actor=actor, contacts=party.contacts)
            _apply_addresses(party=party, workspace=workspace, actor=actor, addresses=party.addresses)
            _apply_documents(party=party, workspace=workspace, actor=actor, documents=party.documents)
            _sync_denormalized_contact_fields(party=party, workspace=workspace)
            party.save(update_fields=["primary_phone", "primary_email", "updated_at", "updated_by"])
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
