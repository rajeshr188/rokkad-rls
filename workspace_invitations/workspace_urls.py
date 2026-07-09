from django.urls import path

from workspace_invitations.views import (
    invitation_collection,
    invitation_resend,
    invitation_resend_page,
    invitation_revoke,
    invitation_revoke_page,
    invitations_page,
)

app_name = "workspace_invitations"

urlpatterns = [
    path("", invitation_collection, name="collection"),
    path("<uuid:invitation_id>/revoke/", invitation_revoke, name="revoke"),
    path("<uuid:invitation_id>/resend/", invitation_resend, name="resend"),
    path("ui/", invitations_page, name="page"),
    path("ui/<uuid:invitation_id>/revoke/", invitation_revoke_page, name="page-revoke"),
    path("ui/<uuid:invitation_id>/resend/", invitation_resend_page, name="page-resend"),
]
