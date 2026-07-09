from django.urls import path

from workspace_invitations.views import invitation_accept, invitation_accept_page

app_name = "workspace_invitations"

urlpatterns = [
    path("accept/<str:token>/ui/", invitation_accept_page, name="accept-page"),
    path("accept/<str:token>/", invitation_accept, name="accept"),
]
