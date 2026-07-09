from functools import wraps

from accounts.verification import require_verified_email
from django.core.exceptions import PermissionDenied

from authorization.policies import require_permission


def workspace_permission_required(permission: str):
    """Require workspace-scoped permission using request.active_workspace."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            workspace = getattr(request, "active_workspace", None)
            if workspace is None:
                raise PermissionDenied("Workspace context is missing.")

            require_verified_email(actor=request.user)
            require_permission(actor=request.user, workspace=workspace, permission=permission)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class WorkspacePermissionRequiredMixin:
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not self.required_permission:
            raise PermissionDenied("required_permission must be configured.")

        workspace = getattr(request, "active_workspace", None)
        if workspace is None:
            raise PermissionDenied("Workspace context is missing.")

        require_verified_email(actor=request.user)
        require_permission(actor=request.user, workspace=workspace, permission=self.required_permission)
        return super().dispatch(request, *args, **kwargs)
