from functools import wraps

from django.core.exceptions import PermissionDenied

from billing.gates import require_workspace_feature


def workspace_feature_required(feature: str, *, methods=None):
    required_methods = {method.upper() for method in methods} if methods else None

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            method = request.method.upper()
            if required_methods is None or method in required_methods:
                workspace = getattr(request, "active_workspace", None)
                if workspace is None:
                    raise PermissionDenied("Workspace context is missing.")
                require_workspace_feature(workspace=workspace, feature=feature)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
