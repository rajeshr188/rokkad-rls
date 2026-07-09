WORKSPACE_ACCESS = "workspace.access"
WORKSPACE_VIEW_DASHBOARD = "workspace.view_dashboard"
MEMBERSHIP_MANAGE = "membership.manage"
MEMBERSHIP_CHANGE_ROLE = "membership.change_role"
MEMBERSHIP_VIEW = "membership.view"
NOTES_VIEW = "notes.view"
NOTES_CREATE = "notes.create"
NOTES_UPDATE = "notes.update"
NOTES_DELETE = "notes.delete"
PARTY_VIEW = "party.view"
PARTY_CREATE = "party.create"
PARTY_UPDATE = "party.update"
PARTY_DELETE = "party.delete"
INVITATION_VIEW = "invitation.view"
INVITATION_MANAGE = "invitation.manage"
BILLING_VIEW = "billing.view"
BILLING_MANAGE = "billing.manage"


ROLE_PERMISSIONS = {
    "owner": {
        WORKSPACE_ACCESS,
        WORKSPACE_VIEW_DASHBOARD,
        MEMBERSHIP_VIEW,
        MEMBERSHIP_MANAGE,
        MEMBERSHIP_CHANGE_ROLE,
        NOTES_VIEW,
        NOTES_CREATE,
        NOTES_UPDATE,
        NOTES_DELETE,
        PARTY_VIEW,
        PARTY_CREATE,
        PARTY_UPDATE,
        PARTY_DELETE,
        INVITATION_VIEW,
        INVITATION_MANAGE,
        BILLING_VIEW,
        BILLING_MANAGE,
    },
    "admin": {
        WORKSPACE_ACCESS,
        WORKSPACE_VIEW_DASHBOARD,
        MEMBERSHIP_VIEW,
        MEMBERSHIP_MANAGE,
        NOTES_VIEW,
        NOTES_CREATE,
        NOTES_UPDATE,
        NOTES_DELETE,
        PARTY_VIEW,
        PARTY_CREATE,
        PARTY_UPDATE,
        PARTY_DELETE,
        INVITATION_VIEW,
        INVITATION_MANAGE,
        BILLING_VIEW,
        BILLING_MANAGE,
    },
    "manager": {
        WORKSPACE_ACCESS,
        WORKSPACE_VIEW_DASHBOARD,
        MEMBERSHIP_VIEW,
        NOTES_VIEW,
        NOTES_CREATE,
        NOTES_UPDATE,
        PARTY_VIEW,
        PARTY_CREATE,
        PARTY_UPDATE,
        INVITATION_VIEW,
        BILLING_VIEW,
    },
    "staff": {
        WORKSPACE_ACCESS,
        WORKSPACE_VIEW_DASHBOARD,
        NOTES_VIEW,
        NOTES_CREATE,
        NOTES_UPDATE,
        PARTY_VIEW,
        PARTY_CREATE,
        PARTY_UPDATE,
    },
    "viewer": {
        WORKSPACE_ACCESS,
        WORKSPACE_VIEW_DASHBOARD,
        NOTES_VIEW,
        PARTY_VIEW,
    },
}
