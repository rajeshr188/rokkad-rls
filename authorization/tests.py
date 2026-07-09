from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.test import TestCase

from allauth.account.models import EmailAddress
from authorization.decorators import workspace_permission_required
from authorization.permissions import MEMBERSHIP_CHANGE_ROLE, MEMBERSHIP_MANAGE
from authorization.policies import get_active_membership, has_permission, require_permission
from memberships.models import WorkspaceMember
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


class AuthorizationPolicyTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="owner_auth", password="pass123")
		self.admin = User.objects.create_user(username="admin_auth", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_auth", password="pass123")
		self.outsider = User.objects.create_user(username="outsider_auth", password="pass123")

		self.workspace = create_workspace(actor=self.owner, payload={"name": "AuthSpace"})
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=self.admin,
			role=WorkspaceMember.Role.ADMIN,
			status=WorkspaceMember.Status.ACTIVE,
		)
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=self.viewer,
			role=WorkspaceMember.Role.VIEWER,
			status=WorkspaceMember.Status.ACTIVE,
		)

	def test_get_active_membership_returns_none_for_outsider(self):
		membership = get_active_membership(actor=self.outsider, workspace=self.workspace)
		self.assertIsNone(membership)

	def test_has_permission_owner_can_change_roles(self):
		self.assertTrue(
			has_permission(
				actor=self.owner,
				workspace=self.workspace,
				permission=MEMBERSHIP_CHANGE_ROLE,
			)
		)

	def test_has_permission_admin_can_manage_members_but_not_change_roles(self):
		self.assertTrue(
			has_permission(
				actor=self.admin,
				workspace=self.workspace,
				permission=MEMBERSHIP_MANAGE,
			)
		)
		self.assertFalse(
			has_permission(
				actor=self.admin,
				workspace=self.workspace,
				permission=MEMBERSHIP_CHANGE_ROLE,
			)
		)

	def test_require_permission_raises_for_viewer(self):
		with self.assertRaises(PermissionDenied):
			require_permission(
				actor=self.viewer,
				workspace=self.workspace,
				permission=MEMBERSHIP_MANAGE,
			)


class AuthorizationDecoratorTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.owner = User.objects.create_user(username="owner_dec", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_dec", password="pass123")
		mark_verified(self.owner)
		mark_verified(self.viewer)
		self.workspace = create_workspace(actor=self.owner, payload={"name": "DecoSpace"})
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=self.viewer,
			role=WorkspaceMember.Role.VIEWER,
			status=WorkspaceMember.Status.ACTIVE,
		)

	def test_workspace_permission_required_allows_owner(self):
		@workspace_permission_required(MEMBERSHIP_MANAGE)
		def view(request):
			return HttpResponse("ok")

		request = self.factory.get("/")
		request.user = self.owner
		request.active_workspace = self.workspace

		response = view(request)
		self.assertEqual(response.status_code, 200)

	def test_workspace_permission_required_rejects_viewer(self):
		@workspace_permission_required(MEMBERSHIP_MANAGE)
		def view(request):
			return HttpResponse("ok")

		request = self.factory.get("/")
		request.user = self.viewer
		request.active_workspace = self.workspace

		with self.assertRaises(PermissionDenied):
			view(request)

	def test_workspace_permission_required_rejects_unverified_user(self):
		@workspace_permission_required(MEMBERSHIP_MANAGE)
		def view(request):
			return HttpResponse("ok")

		unverified = User.objects.create_user(username="unverified_dec", password="pass123")
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=unverified,
			role=WorkspaceMember.Role.ADMIN,
			status=WorkspaceMember.Status.ACTIVE,
		)

		request = self.factory.get("/")
		request.user = unverified
		request.active_workspace = self.workspace

		with self.assertRaises(PermissionDenied):
			view(request)
