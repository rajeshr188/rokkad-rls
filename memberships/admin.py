from django.contrib import admin

from memberships.models import WorkspaceMember


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
	list_display = ("workspace", "user", "role", "status", "joined_at")
	search_fields = ("workspace__name", "user__username")
	list_filter = ("role", "status")
