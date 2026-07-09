from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class AccountRoutesTests(TestCase):
	def test_allauth_login_route_available(self):
		response = self.client.get(reverse("account_login"))
		self.assertEqual(response.status_code, 200)


class ProfilePageTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="profile_user",
			email="profile@example.com",
			password="pass123",
		)

	def test_profile_requires_login(self):
		response = self.client.get(reverse("accounts:profile"))
		self.assertEqual(response.status_code, 302)

	def test_profile_update(self):
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("accounts:profile"),
			data={
				"first_name": "R",
				"last_name": "K",
				"email": "updated@example.com",
			},
		)
		self.assertEqual(response.status_code, 302)

		self.user.refresh_from_db()
		self.assertEqual(self.user.first_name, "R")
		self.assertEqual(self.user.last_name, "K")
		self.assertEqual(self.user.email, "updated@example.com")
