from django.urls import path

from memberships.views import member_role_update, member_role_update_page, members_collection, members_page

app_name = "memberships"

urlpatterns = [
    path("", members_collection, name="collection"),
    path("<uuid:member_id>/role/", member_role_update, name="role-update"),
    path("ui/", members_page, name="page"),
    path("ui/<uuid:member_id>/role/", member_role_update_page, name="page-role-update"),
]
