from django.contrib import admin

from billing.models import BillingWebhookEvent, Plan, Subscription, SubscriptionFeature


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
	list_display = ("code", "name", "is_active", "created_at")
	list_filter = ("is_active",)
	search_fields = ("code", "name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
	list_display = ("workspace", "plan", "state", "current_period_end", "updated_at")
	list_filter = ("state", "plan")
	search_fields = ("workspace__slug", "workspace__name", "provider_subscription_id")


@admin.register(SubscriptionFeature)
class SubscriptionFeatureAdmin(admin.ModelAdmin):
	list_display = ("plan", "key", "enabled", "limit_quantity")
	list_filter = ("enabled", "plan")
	search_fields = ("key", "plan__code")


@admin.register(BillingWebhookEvent)
class BillingWebhookEventAdmin(admin.ModelAdmin):
	list_display = ("provider", "event_id", "event_type", "status", "processed_at")
	list_filter = ("provider", "status", "event_type")
	search_fields = ("event_id",)
