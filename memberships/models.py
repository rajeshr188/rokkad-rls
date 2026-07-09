from django.conf import settings
from django.db import models

from common.models import TenantModel


class WorkspaceMember(TenantModel):

	class Role(models.TextChoices):
		OWNER = "owner", "Owner"
		ADMIN = "admin", "Admin"
		MANAGER = "manager", "Manager"
		STAFF = "staff", "Staff"
		VIEWER = "viewer", "Viewer"

	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INVITED = "invited", "Invited"
		SUSPENDED = "suspended", "Suspended"
		REMOVED = "removed", "Removed"

	workspace = models.ForeignKey(
		"workspaces.Workspace",
		on_delete=models.CASCADE,
		related_name="memberships",
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="workspace_memberships",
	)
	role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	invited_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="workspace_member_invites",
	)
	joined_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["workspace", "user"], name="uniq_workspace_user"),
		]
		indexes = [
			models.Index(fields=["workspace", "role"]),
			models.Index(fields=["user", "status"]),
		]

	def __str__(self):
		return f"{self.user} @ {self.workspace}"
