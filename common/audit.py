from common.models import AuditLog


def log_action(*, actor, workspace, action: str, target_type: str, target_id, metadata=None):
    AuditLog.objects.create(
        actor=actor,
        workspace=workspace,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else "",
        metadata=metadata or {},
    )
