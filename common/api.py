import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse


def error_response(*, status: int, code: str, detail):
    return JsonResponse(
        {
            "error": {
                "code": code,
                "detail": detail,
            }
        },
        status=status,
    )


def parse_json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON payload.") from exc


def validation_error_response(exc: ValidationError, *, code: str = "validation_error", status: int = 400):
    if hasattr(exc, "message_dict"):
        detail = exc.message_dict
    elif hasattr(exc, "messages"):
        detail = exc.messages[0] if len(exc.messages) == 1 else exc.messages
    else:
        detail = str(exc)
    return error_response(status=status, code=code, detail=detail)
