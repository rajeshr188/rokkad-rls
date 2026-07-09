from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TenantModel
from memberships.models import WorkspaceMember


class WorkspaceInvitation(TenantModel):

	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		ACCEPTED = "accepted", "Accepted"
		REVOKED = "revoked", "Revoked"
		EXPIRED = "expired", "Expired"

	workspace = models.ForeignKey(
		"workspaces.Workspace",
		on_delete=models.CASCADE,
		related_name="invitations",
	)
	email = models.EmailField()
	role = models.CharField(max_length=20, choices=WorkspaceMember.Role.choices, default=WorkspaceMember.Role.VIEWER)
	invited_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="sent_workspace_invitations",
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	token = models.CharField(max_length=96, unique=True, db_index=True)
	expires_at = models.DateTimeField()
	accepted_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="accepted_workspace_invitations",
	)
	accepted_at = models.DateTimeField(null=True, blank=True)
	revoked_at = models.DateTimeField(null=True, blank=True)
	last_sent_at = models.DateTimeField(null=True, blank=True)
	resend_count = models.PositiveSmallIntegerField(default=0)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "email", "status"],
				condition=Q(status="pending"),
				name="uniq_workspace_email_pending_invite",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "status"]),
			models.Index(fields=["email", "status"]),
			models.Index(fields=["expires_at"]),
		]

	def __str__(self):
		return f"{self.email} invited to {self.workspace}"
