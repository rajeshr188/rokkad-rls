from django.urls import path

from billing.views import billing_page, checkout_session_api, checkout_success_page

app_name = "billing"

urlpatterns = [
    path("ui/", billing_page, name="page"),
    path("ui/checkout-success/", checkout_success_page, name="checkout-success-page"),
    path("api/checkout-session/", checkout_session_api, name="checkout-session-api"),
]
