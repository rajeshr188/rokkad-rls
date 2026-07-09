from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.verification import has_verified_email
from billing.services import get_public_plan_catalog


def healthz(request):
	db_ok = True
	db_error = ""

	try:
		with connection.cursor() as cursor:
			cursor.execute("SELECT 1")
			cursor.fetchone()
	except Exception as exc:  # pragma: no cover - defensive branch
		db_ok = False
		db_error = str(exc)

	payload = {
		"status": "ok" if db_ok else "degraded",
		"timestamp": timezone.now().isoformat(),
		"checks": {
			"database": {
				"ok": db_ok,
				"vendor": connection.vendor,
				"error": db_error,
			}
		},
	}
	return JsonResponse(payload, status=200 if db_ok else 503)


def landing_page(request):
	is_authenticated = bool(getattr(request, "user", None) and request.user.is_authenticated)
	can_open_app = is_authenticated and has_verified_email(actor=request.user)

	if can_open_app:
		return redirect("workspace-home")

	return render(
		request,
		"public/landing_page.html",
		{
			"plans": get_public_plan_catalog(),
			"is_authenticated": is_authenticated,
			"can_open_app": can_open_app,
		},
	)


def pricing_page(request):
	is_authenticated = bool(getattr(request, "user", None) and request.user.is_authenticated)
	can_open_app = is_authenticated and has_verified_email(actor=request.user)
	return render(
		request,
		"public/pricing_page.html",
		{
			"plans": get_public_plan_catalog(),
			"is_authenticated": is_authenticated,
			"can_open_app": can_open_app,
		},
	)
