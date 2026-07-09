from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from memberships.models import WorkspaceMember
from memberships.services import add_member
from workspace_invitations.models import WorkspaceInvitation
from workspace_invitations.services import (
	accept_invitation,
	create_invitation,
	resend_invitation,
	revoke_invitation,
)
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=user.email,
		defaults={"verified": True, "primary": True},
	)


class WorkspaceInvitationServiceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="owner_inv", email="owner@example.com", password="pass123")
		self.admin = User.objects.create_user(username="admin_inv", email="admin@example.com", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_inv", email="viewer@example.com", password="pass123")
		self.invited_user = User.objects.create_user(
			username="invited_user", email="invitee@example.com", password="pass123"
		)
		self.other_user = User.objects.create_user(username="other_inv", email="other@example.com", password="pass123")

		mark_verified(self.owner)
		mark_verified(self.admin)
		mark_verified(self.viewer)
		mark_verified(self.invited_user)
		mark_verified(self.other_user)

		self.workspace = create_workspace(actor=self.owner, payload={"name": "Invite Space"})
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.admin, "role": WorkspaceMember.Role.ADMIN},
		)
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.viewer, "role": WorkspaceMember.Role.VIEWER},
		)

	def test_create_invitation_rejects_duplicate_pending_invite(self):
		create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.STAFF},
		)

		with self.assertRaises(ValidationError):
			create_invitation(
				actor=self.admin,
				workspace=self.workspace,
				payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.STAFF},
			)

	def test_create_invitation_rejects_already_active_member_email(self):
		with self.assertRaises(ValidationError):
			create_invitation(
				actor=self.admin,
				workspace=self.workspace,
				payload={"email": "viewer@example.com", "role": WorkspaceMember.Role.STAFF},
			)

	def test_create_invitation_denies_viewer(self):
		with self.assertRaises(PermissionDenied):
			create_invitation(
				actor=self.viewer,
				workspace=self.workspace,
				payload={"email": "new@example.com", "role": WorkspaceMember.Role.STAFF},
			)

	def test_accept_invitation_rejects_email_mismatch(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.MANAGER},
		)

		with self.assertRaises(PermissionDenied):
			accept_invitation(actor=self.other_user, token=invitation.token)

	def test_accept_invitation_expiry_and_replay_resistance(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.MANAGER},
		)

		invitation.expires_at = timezone.now() - timedelta(minutes=1)
		invitation.save(update_fields=["expires_at", "updated_at"])

		with self.assertRaises(ValidationError):
			accept_invitation(actor=self.invited_user, token=invitation.token)

		invitation.refresh_from_db()
		self.assertEqual(invitation.status, WorkspaceInvitation.Status.EXPIRED)

	def test_accept_invitation_creates_membership_and_blocks_reuse(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.MANAGER},
		)

		accepted_invitation, membership = accept_invitation(actor=self.invited_user, token=invitation.token)

		self.assertEqual(accepted_invitation.status, WorkspaceInvitation.Status.ACCEPTED)
		self.assertEqual(membership.role, WorkspaceMember.Role.MANAGER)
		self.assertEqual(membership.status, WorkspaceMember.Status.ACTIVE)

		with self.assertRaises(ValidationError):
			accept_invitation(actor=self.invited_user, token=invitation.token)

	def test_revoke_and_resend_pending_invitation(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee@example.com", "role": WorkspaceMember.Role.STAFF},
		)

		original_token = invitation.token
		invitation = resend_invitation(actor=self.admin, workspace=self.workspace, invitation=invitation)
		self.assertNotEqual(invitation.token, original_token)
		self.assertEqual(invitation.resend_count, 1)

		invitation = revoke_invitation(actor=self.admin, workspace=self.workspace, invitation=invitation)
		self.assertEqual(invitation.status, WorkspaceInvitation.Status.REVOKED)


class WorkspaceInvitationEndpointTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="owner_ep_inv", email="owner_ep@example.com", password="pass123")
		self.admin = User.objects.create_user(username="admin_ep_inv", email="admin_ep@example.com", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_ep_inv", email="viewer_ep@example.com", password="pass123")
		self.invited_user = User.objects.create_user(
			username="invitee_ep", email="invitee_ep@example.com", password="pass123"
		)

		mark_verified(self.owner)
		mark_verified(self.admin)
		mark_verified(self.viewer)
		mark_verified(self.invited_user)

		self.workspace = create_workspace(actor=self.owner, payload={"name": "Invite Endpoint Space"})
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.admin, "role": WorkspaceMember.Role.ADMIN},
		)
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.viewer, "role": WorkspaceMember.Role.VIEWER},
		)

	def test_admin_can_create_and_list_invitations(self):
		self.client.force_login(self.admin)

		created = self.client.post(
			f"/w/{self.workspace.slug}/invitations/",
			data={"email": "invitee_ep@example.com", "role": WorkspaceMember.Role.STAFF},
			content_type="application/json",
		)
		self.assertEqual(created.status_code, 201)

		listed = self.client.get(f"/w/{self.workspace.slug}/invitations/")
		self.assertEqual(listed.status_code, 200)
		self.assertEqual(len(listed.json()["items"]), 1)

	def test_viewer_cannot_create_invitation(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/w/{self.workspace.slug}/invitations/",
			data={"email": "x@example.com", "role": WorkspaceMember.Role.STAFF},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 403)

	def test_accept_endpoint_honors_token_single_use(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee_ep@example.com", "role": WorkspaceMember.Role.STAFF},
		)

		self.client.force_login(self.invited_user)
		accepted = self.client.post(f"/invitations/accept/{invitation.token}/")
		self.assertEqual(accepted.status_code, 200)
		self.assertEqual(accepted.json()["invitation"]["status"], WorkspaceInvitation.Status.ACCEPTED)

		replay = self.client.post(f"/invitations/accept/{invitation.token}/")
		self.assertEqual(replay.status_code, 400)
		self.assertEqual(replay.json()["error"]["code"], "invalid_invitation")

	def test_invitation_management_page_visible_for_admin(self):
		self.client.force_login(self.admin)
		response = self.client.get(
			reverse("workspaces:workspace_invitations:page", kwargs={"workspace_slug": self.workspace.slug})
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Send Invitation")

	def test_invitation_management_page_read_only_for_manager(self):
		manager = User.objects.create_user(username="manager_ep_inv", email="manager_ep@example.com", password="pass123")
		mark_verified(manager)
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": manager, "role": WorkspaceMember.Role.MANAGER},
		)

		self.client.force_login(manager)
		response = self.client.get(
			reverse("workspaces:workspace_invitations:page", kwargs={"workspace_slug": self.workspace.slug})
		)
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "Send Invitation")

	def test_accept_page_renders_for_valid_token(self):
		invitation = create_invitation(
			actor=self.admin,
			workspace=self.workspace,
			payload={"email": "invitee_ep@example.com", "role": WorkspaceMember.Role.STAFF},
		)

		self.client.force_login(self.invited_user)
		response = self.client.get(reverse("workspace_invitations:accept-page", kwargs={"token": invitation.token}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.workspace.name)
