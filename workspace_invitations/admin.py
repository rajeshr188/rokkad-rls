from django.contrib import admin

from workspace_invitations.models import WorkspaceInvitation


@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(admin.ModelAdmin):
	list_display = ("email", "workspace", "role", "status", "expires_at", "invited_by", "created_at")
	list_filter = ("status", "role", "workspace")
	search_fields = ("email", "token", "workspace__slug")
