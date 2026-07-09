from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from allauth.account.models import EmailAddress
from billing.models import Subscription
from billing.services import transition_subscription_state
from common.models import AuditLog
from memberships.models import WorkspaceMember
from memberships.services import add_member, change_member_role, require_active_membership
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


class MembershipServicesTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="owner", password="pass123")
		self.admin = User.objects.create_user(username="admin", password="pass123")
		self.staff = User.objects.create_user(username="staff", password="pass123")
		self.new_user = User.objects.create_user(username="new", password="pass123")

		self.workspace = create_workspace(actor=self.owner, payload={"name": "Acme"})
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=self.admin,
			role=WorkspaceMember.Role.ADMIN,
			status=WorkspaceMember.Status.ACTIVE,
		)
		WorkspaceMember.objects.create(
			workspace=self.workspace,
			user=self.staff,
			role=WorkspaceMember.Role.STAFF,
			status=WorkspaceMember.Status.ACTIVE,
		)

	def test_require_active_membership_returns_membership(self):
		membership = require_active_membership(actor=self.owner, workspace=self.workspace)
		self.assertEqual(membership.role, WorkspaceMember.Role.OWNER)

	def test_add_member_allows_admin(self):
		membership = add_member(
			actor=self.admin,
			workspace=self.workspace,
			payload={"user": self.new_user, "role": WorkspaceMember.Role.VIEWER},
		)
		self.assertEqual(membership.user, self.new_user)
		self.assertEqual(membership.status, WorkspaceMember.Status.ACTIVE)

	def test_add_member_denies_staff(self):
		with self.assertRaises(PermissionDenied):
			add_member(
				actor=self.staff,
				workspace=self.workspace,
				payload={"user": self.new_user, "role": WorkspaceMember.Role.VIEWER},
			)

	def test_change_member_role_only_owner_allowed(self):
		member = WorkspaceMember.objects.get(workspace=self.workspace, user=self.staff)

		with self.assertRaises(PermissionDenied):
			change_member_role(
				actor=self.admin,
				workspace=self.workspace,
				membership=member,
				new_role=WorkspaceMember.Role.MANAGER,
			)

		updated = change_member_role(
			actor=self.owner,
			workspace=self.workspace,
			membership=member,
			new_role=WorkspaceMember.Role.MANAGER,
		)
		self.assertEqual(updated.role, WorkspaceMember.Role.MANAGER)

	def test_add_member_rejects_duplicate_active_membership(self):
		with self.assertRaises(ValidationError):
			add_member(
				actor=self.owner,
				workspace=self.workspace,
				payload={"user": self.staff, "role": WorkspaceMember.Role.STAFF},
			)

	def test_add_member_writes_audit_log(self):
		membership = add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.new_user, "role": WorkspaceMember.Role.VIEWER},
		)

		audit = AuditLog.objects.filter(action="membership.created", target_id=str(membership.id)).first()
		self.assertIsNotNone(audit)
		self.assertEqual(audit.workspace, self.workspace)

	def test_change_member_role_writes_audit_log(self):
		member = WorkspaceMember.objects.get(workspace=self.workspace, user=self.staff)
		updated = change_member_role(
			actor=self.owner,
			workspace=self.workspace,
			membership=member,
			new_role=WorkspaceMember.Role.MANAGER,
		)

		audit = AuditLog.objects.filter(action="membership.role_updated", target_id=str(updated.id)).first()
		self.assertIsNotNone(audit)


class MembershipEndpointTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="ep_owner", password="pass123")
		self.admin = User.objects.create_user(username="ep_admin", password="pass123")
		self.viewer = User.objects.create_user(username="ep_viewer", password="pass123")
		self.target = User.objects.create_user(username="ep_target", password="pass123")
		mark_verified(self.owner)
		mark_verified(self.admin)
		mark_verified(self.viewer)
		mark_verified(self.target)
		self.workspace = create_workspace(actor=self.owner, payload={"name": "EndpointSpace"})
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

	def test_members_list_for_viewer(self):
		self.client.force_login(self.admin)
		response = self.client.get(f"/w/{self.workspace.slug}/members/")
		self.assertEqual(response.status_code, 200)

	def test_add_member_as_admin(self):
		self.client.force_login(self.admin)
		response = self.client.post(
			f"/w/{self.workspace.slug}/members/",
			data={"user_id": self.target.id, "role": WorkspaceMember.Role.STAFF},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 201)

	def test_membership_endpoint_returns_standardized_error(self):
		self.client.force_login(self.admin)
		response = self.client.post(
			f"/w/{self.workspace.slug}/members/",
			data={"role": WorkspaceMember.Role.STAFF},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], "missing_field")

	def test_membership_write_blocked_by_feature_gate(self):
		transition_subscription_state(
			subscription=self.workspace.subscription,
			new_state=Subscription.State.CANCELED,
		)

		self.client.force_login(self.admin)
		response = self.client.post(
			f"/w/{self.workspace.slug}/members/",
			data={"user_id": self.target.id, "role": WorkspaceMember.Role.STAFF},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json()["error"]["code"], "permission_denied")

	def test_change_member_role_owner_only(self):
		member = WorkspaceMember.objects.get(workspace=self.workspace, user=self.viewer)

		self.client.force_login(self.admin)
		denied = self.client.patch(
			f"/w/{self.workspace.slug}/members/{member.id}/role/",
			data={"role": WorkspaceMember.Role.MANAGER},
			content_type="application/json",
		)
		self.assertEqual(denied.status_code, 403)

		self.client.force_login(self.owner)
		ok = self.client.patch(
			f"/w/{self.workspace.slug}/members/{member.id}/role/",
			data={"role": WorkspaceMember.Role.MANAGER},
			content_type="application/json",
		)
		self.assertEqual(ok.status_code, 200)
