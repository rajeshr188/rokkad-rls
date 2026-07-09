from functools import wraps

from accounts.verification import require_verified_email


def verified_email_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        require_verified_email(actor=request.user)
        return view_func(request, *args, **kwargs)

    return _wrapped
