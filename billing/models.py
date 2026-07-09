from django.db import models

from common.models import TenantModel, TimeStampedModel, UUIDModel


class Plan(UUIDModel, TimeStampedModel):
	code = models.SlugField(max_length=64, unique=True)
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return self.name


class Subscription(TenantModel):

	class State(models.TextChoices):
		TRIALING = "trialing", "Trialing"
		ACTIVE = "active", "Active"
		PAST_DUE = "past_due", "Past Due"
		CANCELED = "canceled", "Canceled"
		EXPIRED = "expired", "Expired"

	workspace = models.OneToOneField(
		"workspaces.Workspace",
		on_delete=models.CASCADE,
		related_name="subscription",
	)
	plan = models.ForeignKey("billing.Plan", on_delete=models.PROTECT, related_name="subscriptions")
	state = models.CharField(max_length=20, choices=State.choices, default=State.TRIALING)
	trial_ends_at = models.DateTimeField(null=True, blank=True)
	current_period_start = models.DateTimeField(null=True, blank=True)
	current_period_end = models.DateTimeField(null=True, blank=True)
	canceled_at = models.DateTimeField(null=True, blank=True)
	provider = models.CharField(max_length=32, blank=True)
	provider_subscription_id = models.CharField(max_length=128, blank=True)

	class Meta:
		indexes = [
			models.Index(fields=["state"]),
			models.Index(fields=["current_period_end"]),
		]

	def __str__(self):
		return f"{self.workspace} subscription ({self.state})"


class SubscriptionFeature(UUIDModel, TimeStampedModel):
	plan = models.ForeignKey("billing.Plan", on_delete=models.CASCADE, related_name="features")
	key = models.CharField(max_length=120)
	enabled = models.BooleanField(default=True)
	limit_quantity = models.PositiveIntegerField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["plan", "key"], name="uniq_plan_feature_key"),
		]
		indexes = [
			models.Index(fields=["key", "enabled"]),
		]

	def __str__(self):
		return f"{self.plan.code}:{self.key}"


class BillingWebhookEvent(UUIDModel, TimeStampedModel):
	class Status(models.TextChoices):
		RECEIVED = "received", "Received"
		PROCESSED = "processed", "Processed"
		FAILED = "failed", "Failed"

	provider = models.CharField(max_length=32)
	event_id = models.CharField(max_length=128)
	event_type = models.CharField(max_length=128, blank=True)
	status = models.CharField(max_length=24, choices=Status.choices, default=Status.RECEIVED)
	payload = models.JSONField(default=dict, blank=True)
	processed_at = models.DateTimeField(null=True, blank=True)
	error_message = models.TextField(blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_provider_event_id"),
		]
		indexes = [
			models.Index(fields=["provider", "status"]),
			models.Index(fields=["provider", "processed_at"]),
		]

	def __str__(self):
		return f"{self.provider}:{self.event_id} ({self.status})"
