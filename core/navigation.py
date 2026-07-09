from dataclasses import dataclass

from django.urls import reverse

from accounts.verification import has_verified_email
from authorization.policies import has_permission
from authorization.permissions import BILLING_VIEW, INVITATION_VIEW, MEMBERSHIP_VIEW, NOTES_VIEW, WORKSPACE_VIEW_DASHBOARD
from billing.constants import FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE
from billing.gates import has_workspace_feature
from workspaces.services import list_user_workspaces


@dataclass(frozen=True)
class NavEntry:
    label: str
    route_name: str
    requires_workspace: bool = False
    required_permission: str | None = None
    required_feature: str | None = None


GLOBAL_NAV = (
    NavEntry(label="Home", route_name="workspace-home"),
    NavEntry(label="Create Workspace", route_name="workspace-create"),
    NavEntry(label="Pricing", route_name="pricing-page"),
)


ACCOUNT_NAV = (
    NavEntry(label="Profile", route_name="accounts:profile"),
    NavEntry(label="Email", route_name="account_email"),
    NavEntry(label="Password", route_name="account_change_password"),
)


WORKSPACE_NAV = (
    NavEntry(
        label="Dashboard",
        route_name="workspaces:dashboard-page",
        requires_workspace=True,
        required_permission=WORKSPACE_VIEW_DASHBOARD,
    ),
    NavEntry(
        label="Members",
        route_name="workspaces:memberships:page",
        requires_workspace=True,
        required_permission=MEMBERSHIP_VIEW,
        required_feature=FEATURE_MEMBERSHIPS_WRITE,
    ),
    NavEntry(
        label="Notes",
        route_name="workspaces:notes:page",
        requires_workspace=True,
        required_permission=NOTES_VIEW,
        required_feature=FEATURE_NOTES_WRITE,
    ),
    NavEntry(
        label="Invitations",
        route_name="workspaces:workspace_invitations:page",
        requires_workspace=True,
        required_permission=INVITATION_VIEW,
    ),
    NavEntry(
        label="Billing",
        route_name="workspaces:billing:page",
        requires_workspace=True,
        required_permission=BILLING_VIEW,
    ),
)


def get_navigation_sections(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "global": [
                {"label": "Home", "href": reverse("landing-page")},
                {"label": "Pricing", "href": reverse("pricing-page")},
            ],
            "workspace": [],
            "account": [
                {"label": "Login", "href": reverse("account_login")},
                {"label": "Signup", "href": reverse("account_signup")},
            ],
            "admin": [],
        }

    global_items = [{"label": entry.label, "href": reverse(entry.route_name)} for entry in GLOBAL_NAV]
    account_items = [{"label": entry.label, "href": reverse(entry.route_name)} for entry in ACCOUNT_NAV]
    workspace_items = []
    admin_items = []

    if not has_verified_email(actor=user):
        account_items.append({"label": "Verify Email", "href": reverse("account_email")})

    workspace = getattr(request, "active_workspace", None)
    if workspace:
        for entry in WORKSPACE_NAV:
            if entry.required_permission and not has_permission(
                actor=user,
                workspace=workspace,
                permission=entry.required_permission,
            ):
                continue

            if entry.required_feature and not has_workspace_feature(workspace=workspace, feature=entry.required_feature):
                continue

            workspace_items.append(
                {
                    "label": entry.label,
                    "href": reverse(entry.route_name, kwargs={"workspace_slug": workspace.slug}),
                }
            )

    if user.is_staff:
        admin_items.append({"label": "Admin", "href": "/admin/"})

    account_items.append({"label": "Logout", "href": reverse("account_logout")})
    return {
        "global": global_items,
        "workspace": workspace_items,
        "account": account_items,
        "admin": admin_items,
    }


def get_navigation_items(request):
    sections = get_navigation_sections(request)
    return [*sections["global"], *sections["workspace"], *sections["account"], *sections["admin"]]


def get_workspace_switcher_items(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not has_verified_email(actor=user):
        return []

    active_workspace = getattr(request, "active_workspace", None)
    workspaces = list_user_workspaces(actor=user)
    items = [
        {
            "label": "Public",
            "slug": "",
            "href": reverse("workspace-home"),
            "is_active": active_workspace is None,
        }
    ]
    items.extend([
        {
            "label": workspace.name,
            "slug": workspace.slug,
            "href": reverse("workspaces:dashboard-page", kwargs={"workspace_slug": workspace.slug}),
            "is_active": getattr(active_workspace, "slug", None) == workspace.slug,
        }
        for workspace in workspaces
    ])
    return items


def get_workspace_switcher_state(request):
    active_workspace = getattr(request, "active_workspace", None)
    if active_workspace is not None:
        return {"label": active_workspace.name, "is_public": False}
    return {"label": "Switch Workspace", "is_public": True}
