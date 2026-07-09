from django.urls import include, path

from workspaces.views import workspace_complete_onboarding, workspace_dashboard, workspace_dashboard_page

app_name = "workspaces"

urlpatterns = [
    path("", workspace_dashboard, name="dashboard"),
    path("ui/", workspace_dashboard_page, name="dashboard-page"),
    path("onboarding/complete/", workspace_complete_onboarding, name="complete-onboarding"),
    path("billing/", include(("billing.urls", "billing"), namespace="billing")),
    path("members/", include(("memberships.urls", "memberships"), namespace="memberships")),
    path("notes/", include(("notes.urls", "notes"), namespace="notes")),
    path(
        "invitations/",
        include(("workspace_invitations.workspace_urls", "workspace_invitations"), namespace="workspace_invitations"),
    ),
]
