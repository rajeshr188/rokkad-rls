from django.urls import path

from notes.views import note_delete_page, note_detail, notes_collection, notes_page

app_name = "notes"

urlpatterns = [
    path("", notes_collection, name="collection"),
    path("<uuid:note_id>/", note_detail, name="detail"),
    path("ui/", notes_page, name="page"),
    path("ui/<uuid:note_id>/delete/", note_delete_page, name="page-delete"),
]
