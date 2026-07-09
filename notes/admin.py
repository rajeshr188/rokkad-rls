from django.contrib import admin

from notes.models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
	list_display = ("title", "workspace", "created_by", "created_at")
	search_fields = ("title", "workspace__name", "created_by__username")
	list_filter = ("workspace",)
