from django.conf import settings
from django.db import models

from common.models import TimeStampedModel, UUIDModel


class Workspace(UUIDModel, TimeStampedModel):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		SUSPENDED = "suspended", "Suspended"
		ARCHIVED = "archived", "Archived"

	class OnboardingState(models.TextChoices):
		PENDING = "pending", "Pending"
		READY = "ready", "Ready"
		COMPLETED = "completed", "Completed"

	name = models.CharField(max_length=120)
	slug = models.SlugField(max_length=120, unique=True)
	owner = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name="owned_workspaces",
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	onboarding_state = models.CharField(
		max_length=20,
		choices=OnboardingState.choices,
		default=OnboardingState.PENDING,
	)
	onboarding_ready_at = models.DateTimeField(null=True, blank=True)
	onboarding_metadata = models.JSONField(default=dict, blank=True)

	class Meta:
		ordering = ["name"]
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["onboarding_state"]),
		]

	def __str__(self):
		return self.name
