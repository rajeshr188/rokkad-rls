from django.contrib import admin

from common.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
	list_display = ("action", "workspace", "actor", "created_at")
	search_fields = ("action", "target_type", "target_id")
	list_filter = ("action", "created_at")
	readonly_fields = ("created_at",)
