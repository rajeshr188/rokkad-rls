import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

	class Meta:
		abstract = True


class TimeStampedModel(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		abstract = True


class TenantModel(UUIDModel, TimeStampedModel):
	"""Base contract for tenant business data protected by workspace-scoped RLS."""

	tenant_rls_required = True

	workspace = models.ForeignKey(
		"workspaces.Workspace",
		on_delete=models.CASCADE,
		related_name="%(class)ss",
		db_index=True,
	)

	class Meta:
		abstract = True


class TenantScopedModel(TenantModel):
	"""TenantModel variant that tracks who created the row."""

	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="%(class)s_created",
	)

	class Meta:
		abstract = True


class AuditLog(UUIDModel):
	tenant_rls_required = True

	actor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="audit_logs",
	)
	workspace = models.ForeignKey(
		"workspaces.Workspace",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="audit_logs",
	)
	action = models.CharField(max_length=128)
	target_type = models.CharField(max_length=128, blank=True)
	target_id = models.CharField(max_length=128, blank=True)
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["workspace", "created_at"]),
			models.Index(fields=["actor", "created_at"]),
			models.Index(fields=["action", "created_at"]),
		]

	def __str__(self):
		return f"{self.action} ({self.created_at:%Y-%m-%d %H:%M:%S})"
