from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps

from common.models import TenantModel


@dataclass(frozen=True)
class TenantModelSpec:
    model: type
    table_name: str
    workspace_column: str


def _is_tenant_model(model: type) -> bool:
    if getattr(model._meta, "abstract", False) or getattr(model._meta, "proxy", False):
        return False

    if issubclass(model, TenantModel):
        return True

    # Legacy compatibility for existing models until all tenant models inherit TenantModel.
    return bool(getattr(model, "tenant_rls_required", False))


def iter_tenant_model_specs() -> list[TenantModelSpec]:
    specs: list[TenantModelSpec] = []

    for model in apps.get_models():
        if not _is_tenant_model(model):
            continue

        try:
            workspace_field = model._meta.get_field("workspace")
        except Exception as exc:
            raise RuntimeError(
                f"Tenant model {model._meta.label} must define a workspace field."
            ) from exc

        specs.append(
            TenantModelSpec(
                model=model,
                table_name=model._meta.db_table,
                workspace_column=workspace_field.column,
            )
        )

    specs.sort(key=lambda item: item.model._meta.label)
    return specs
