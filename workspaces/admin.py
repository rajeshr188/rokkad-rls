from django.contrib import admin

from workspaces.models import Workspace


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
	list_display = ("name", "slug", "owner", "status", "created_at")
	search_fields = ("name", "slug", "owner__username")
	list_filter = ("status",)
