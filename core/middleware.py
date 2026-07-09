from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import JsonResponse
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

from accounts.verification import require_verified_email
from core.db import (
    apply_actor_context,
    apply_workspace_context,
    clear_actor_context,
    clear_invitation_token_context,
    clear_workspace_context,
)
from workspaces.services import get_workspace_for_user


class WorkspaceContextMiddleware(MiddlewareMixin):
    """Resolve request.active_workspace from URL context for workspace-scoped routes."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.active_workspace = None

        workspace_slug = view_kwargs.get("workspace_slug")
        if not workspace_slug:
            return None

        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication is required for workspace routes.")

        require_verified_email(actor=request.user)

        request.active_workspace = get_workspace_for_user(
            actor=request.user,
            workspace_slug=workspace_slug,
        )
        return None


class RequestRateLimitMiddleware(MiddlewareMixin):
    """Simple per-IP rate limiter for auth and write-heavy endpoints."""

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    LOGIN_PATH_PREFIXES = (
        "/accounts/login/",
        "/accounts/signup/",
        "/accounts/password/reset/",
    )
    WRITE_PATH_PREFIXES = (
        "/w/",
        "/invitations/accept/",
    )

    def process_request(self, request):
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return None

        method = request.method.upper()
        path = request.path or ""
        client_ip = self._client_ip(request)

        if method in self.WRITE_METHODS and path.startswith(self.LOGIN_PATH_PREFIXES):
            if self._exceeded(key=f"rl:login:{client_ip}", limit=settings.RATE_LIMIT_LOGIN_MAX_REQUESTS):
                return self._limited_response(request, scope="login")

        if method in self.WRITE_METHODS and path.startswith(self.WRITE_PATH_PREFIXES):
            if self._exceeded(key=f"rl:write:{client_ip}", limit=settings.RATE_LIMIT_WRITE_MAX_REQUESTS):
                return self._limited_response(request, scope="write")

        return None

    def _exceeded(self, *, key: str, limit: int) -> bool:
        ttl = getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
        if cache.add(key, 1, timeout=ttl):
            return False
        count = cache.incr(key)
        return count > max(limit, 1)

    @staticmethod
    def _client_ip(request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    @staticmethod
    def _limited_response(request, *, scope: str):
        detail = f"Rate limit exceeded for {scope} requests."
        if "application/json" in (request.headers.get("Accept", "") or "") or request.path.startswith("/w/"):
            return JsonResponse(
                {
                    "error": {
                        "code": "rate_limited",
                        "detail": detail,
                    }
                },
                status=429,
            )
        return HttpResponse(detail, status=429)


class RLSContextMiddleware(MiddlewareMixin):
    """Set request-scoped PostgreSQL context used by tenant RLS policies."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.rls_context_applied = False

        if connection.vendor != "postgresql":
            # SQLite/dev fallback: keep bootstrapping simple while still exposing state.
            return None

        # Fail closed for pooled connections by clearing stale context before setting fresh values.
        clear_workspace_context()
        clear_actor_context()
        clear_invitation_token_context()

        if request.user.is_authenticated:
            apply_actor_context(request.user.id)

        workspace = getattr(request, "active_workspace", None)
        if workspace is None:
            return None

        request.rls_context_applied = apply_workspace_context(workspace.id)
        return None
