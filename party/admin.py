from django.contrib import admin

from party.models import Party


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
	list_display = ("name", "party_type", "workspace", "is_active", "created_at")
	list_filter = ("party_type", "workspace", "is_active")
	search_fields = ("name", "workspace__name")
