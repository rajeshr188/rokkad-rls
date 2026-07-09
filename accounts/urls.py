from django.urls import path

from accounts.views import profile_page

app_name = "accounts"

urlpatterns = [
	path("profile/", profile_page, name="profile"),
]
