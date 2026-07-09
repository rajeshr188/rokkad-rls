from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from allauth.account.models import EmailAddress
from billing.models import Subscription
from billing.services import transition_subscription_state

from core.db import apply_workspace_context
from common.models import AuditLog
from memberships.models import WorkspaceMember
from memberships.services import add_member
from workspaces.models import Workspace
from workspaces.services import create_workspace, get_workspace_for_user, list_user_workspaces


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


class WorkspaceServicesTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="owner", password="pass123")
		self.other = User.objects.create_user(username="other", password="pass123")

	def test_create_workspace_creates_owner_membership(self):
		workspace = create_workspace(actor=self.user, payload={"name": "Acme Workspace"})

		self.assertEqual(workspace.owner, self.user)
		member = WorkspaceMember.objects.get(workspace=workspace, user=self.user)
		self.assertEqual(member.role, WorkspaceMember.Role.OWNER)
		self.assertEqual(member.status, WorkspaceMember.Status.ACTIVE)

	def test_get_workspace_for_user_denies_non_member(self):
		workspace = create_workspace(actor=self.user, payload={"name": "Private"})

		with self.assertRaises(PermissionDenied):
			get_workspace_for_user(actor=self.other, workspace_slug=workspace.slug)

	def test_list_user_workspaces_returns_only_active_memberships(self):
		workspace = create_workspace(actor=self.user, payload={"name": "Acme"})
		WorkspaceMember.objects.create(
			workspace=workspace,
			user=self.other,
			role=WorkspaceMember.Role.VIEWER,
			status=WorkspaceMember.Status.SUSPENDED,
		)

		self.assertEqual(list(list_user_workspaces(actor=self.other)), [])

	def test_list_user_workspaces_includes_active_memberships(self):
		workspace = create_workspace(actor=self.user, payload={"name": "Shared Space"})
		WorkspaceMember.objects.update_or_create(
			workspace=workspace,
			user=self.other,
			defaults={
				"role": WorkspaceMember.Role.VIEWER,
				"status": WorkspaceMember.Status.ACTIVE,
			},
		)

		result = list(list_user_workspaces(actor=self.other))
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].slug, workspace.slug)


class WorkspaceDashboardRouteTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="route_owner", password="pass123")
		self.other = User.objects.create_user(username="route_other", password="pass123")
		mark_verified(self.owner)
		mark_verified(self.other)
		self.workspace = create_workspace(actor=self.owner, payload={"name": "Route Space"})

	def test_dashboard_returns_workspace_payload_for_member(self):
		self.client.force_login(self.owner)
		url = reverse("workspaces:dashboard", kwargs={"workspace_slug": self.workspace.slug})
		response = self.client.get(url)

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["workspace"]["slug"], self.workspace.slug)

	def test_dashboard_denies_non_member(self):
		self.client.force_login(self.other)
		url = reverse("workspaces:dashboard", kwargs={"workspace_slug": self.workspace.slug})
		response = self.client.get(url)

		self.assertEqual(response.status_code, 403)


class WorkspaceSignalsTests(TestCase):
	def test_workspace_create_auto_adds_owner_membership(self):
		owner = User.objects.create_user(username="signal_owner", password="pass123")
		workspace = Workspace.objects.create(name="Signal Space", slug="signal-space", owner=owner)

		apply_workspace_context(workspace.id)
		self.assertTrue(
			WorkspaceMember.objects.filter(
				workspace=workspace,
				user=owner,
				role=WorkspaceMember.Role.OWNER,
				status=WorkspaceMember.Status.ACTIVE,
			).exists()
		)


class WorkspaceHomePageTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="home_user", password="pass123")
		self.other = User.objects.create_user(username="home_other", password="pass123")
		mark_verified(self.user)
		mark_verified(self.other)
		self.workspace = create_workspace(actor=self.user, payload={"name": "Home Space"})

	def test_home_requires_login(self):
		response = self.client.get(reverse("workspace-home"))
		self.assertEqual(response.status_code, 302)

	def test_home_lists_only_user_workspaces(self):
		create_workspace(actor=self.other, payload={"name": "Other Space"})

		self.client.force_login(self.user)
		response = self.client.get(reverse("workspace-home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.workspace.slug)
		self.assertNotContains(response, "other-space")
		self.assertContains(response, reverse("workspace-create"))
		self.assertContains(response, "Switch Workspace")
		self.assertContains(response, ">Public<", html=False)
		self.assertContains(response, reverse("workspaces:dashboard-page", kwargs={"workspace_slug": self.workspace.slug}))

	def test_home_lists_member_workspace_for_non_owner(self):
		owner = User.objects.create_user(username="member_home_owner", password="pass123")
		member = User.objects.create_user(username="member_home_user", password="pass123")
		mark_verified(owner)
		mark_verified(member)
		workspace = create_workspace(actor=owner, payload={"name": "Collaborative Space"})
		WorkspaceMember.objects.update_or_create(
			workspace=workspace,
			user=member,
			defaults={
				"role": WorkspaceMember.Role.VIEWER,
				"status": WorkspaceMember.Status.ACTIVE,
			},
		)

		self.client.force_login(member)
		response = self.client.get(reverse("workspace-home"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, workspace.slug)


class WorkspaceEmailVerificationRouteTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="email_guard_user", password="pass123")
		self.workspace = create_workspace(actor=self.user, payload={"name": "Email Guard Space"})

	def test_workspace_route_denies_unverified_user(self):
		self.client.force_login(self.user)
		url = reverse("workspaces:dashboard", kwargs={"workspace_slug": self.workspace.slug})
		response = self.client.get(url)
		self.assertEqual(response.status_code, 403)

	def test_workspace_route_allows_verified_user(self):
		mark_verified(self.user)
		self.client.force_login(self.user)
		url = reverse("workspaces:dashboard", kwargs={"workspace_slug": self.workspace.slug})
		response = self.client.get(url)
		self.assertEqual(response.status_code, 200)

	def test_home_denies_unverified_user(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("workspace-home"))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("account_email_verification_sent"))

	def test_home_allows_verified_user(self):
		mark_verified(self.user)
		self.client.force_login(self.user)
		response = self.client.get(reverse("workspace-home"))
		self.assertEqual(response.status_code, 200)

	def test_create_page_redirects_unverified_user(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("workspace-create"))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("account_email_verification_sent"))


class WorkspaceCreatePageTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="create_ui_user", password="pass123")
		mark_verified(self.user)

	def test_create_page_requires_login(self):
		response = self.client.get(reverse("workspace-create"))
		self.assertEqual(response.status_code, 302)

	def test_create_page_renders_for_verified_user(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("workspace-create"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Create Workspace")

	def test_create_page_creates_workspace_and_redirects(self):
		self.client.force_login(self.user)
		response = self.client.post(reverse("workspace-create"), data={"name": "UI Created Workspace"})
		self.assertEqual(response.status_code, 302)
		workspace = Workspace.objects.get(name="UI Created Workspace")
		self.assertEqual(
			response["Location"],
			reverse("workspaces:dashboard-page", kwargs={"workspace_slug": workspace.slug}),
		)


class WorkspaceNavigationVisibilityTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="nav_owner", password="pass123")
		self.viewer = User.objects.create_user(username="nav_viewer", password="pass123")
		mark_verified(self.owner)
		mark_verified(self.viewer)

		self.workspace = create_workspace(actor=self.owner, payload={"name": "Navigation Space"})
		add_member(
			actor=self.owner,
			workspace=self.workspace,
			payload={"user": self.viewer, "role": WorkspaceMember.Role.VIEWER},
		)

	def test_owner_navigation_shows_members_and_notes(self):
		self.client.force_login(self.owner)
		response = self.client.get(reverse("workspaces:dashboard-page", kwargs={"workspace_slug": self.workspace.slug}))

		members_href = reverse("workspaces:memberships:page", kwargs={"workspace_slug": self.workspace.slug})
		notes_href = reverse("workspaces:notes:page", kwargs={"workspace_slug": self.workspace.slug})
		self.assertContains(response, self.workspace.name)
		self.assertContains(response, ">Public<", html=False)
		self.assertContains(response, "Workspace")
		self.assertContains(response, "Account")
		self.assertContains(response, members_href)
		self.assertContains(response, notes_href)

	def test_viewer_navigation_hides_members_but_shows_notes(self):
		self.client.force_login(self.viewer)
		response = self.client.get(reverse("workspaces:dashboard-page", kwargs={"workspace_slug": self.workspace.slug}))

		members_href = reverse("workspaces:memberships:page", kwargs={"workspace_slug": self.workspace.slug})
		notes_href = reverse("workspaces:notes:page", kwargs={"workspace_slug": self.workspace.slug})
		self.assertNotContains(response, members_href)
		self.assertContains(response, notes_href)

	def test_canceled_subscription_hides_feature_gated_links(self):
		transition_subscription_state(
			subscription=self.workspace.subscription,
			new_state=Subscription.State.CANCELED,
		)

		self.client.force_login(self.owner)
		response = self.client.get(reverse("workspaces:dashboard-page", kwargs={"workspace_slug": self.workspace.slug}))

		members_href = reverse("workspaces:memberships:page", kwargs={"workspace_slug": self.workspace.slug})
		notes_href = reverse("workspaces:notes:page", kwargs={"workspace_slug": self.workspace.slug})
		self.assertNotContains(response, members_href)
		self.assertNotContains(response, notes_href)

	def test_dashboard_shows_onboarding_prompt_when_ready(self):
		self.workspace.onboarding_state = Workspace.OnboardingState.READY
		self.workspace.onboarding_metadata = {"source": "test"}
		self.workspace.save(update_fields=["onboarding_state", "onboarding_metadata", "updated_at"])

		self.client.force_login(self.owner)
		response = self.client.get(reverse("workspaces:dashboard-page", kwargs={"workspace_slug": self.workspace.slug}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Onboarding is ready")
		self.assertContains(
			response,
			reverse("workspaces:workspace_invitations:page", kwargs={"workspace_slug": self.workspace.slug}),
		)

	def test_complete_onboarding_endpoint_marks_workspace_completed(self):
		self.workspace.onboarding_state = Workspace.OnboardingState.READY
		self.workspace.onboarding_metadata = {"source": "webhook"}
		self.workspace.save(update_fields=["onboarding_state", "onboarding_metadata", "updated_at"])

		self.client.force_login(self.owner)
		response = self.client.post(reverse("workspaces:complete-onboarding", kwargs={"workspace_slug": self.workspace.slug}))
		self.assertEqual(response.status_code, 302)

		self.workspace.refresh_from_db()
		self.assertEqual(self.workspace.onboarding_state, Workspace.OnboardingState.COMPLETED)
		self.assertTrue(self.workspace.onboarding_metadata.get("completed"))
		self.assertEqual(self.workspace.onboarding_metadata.get("source"), "dashboard_action")

		audit = AuditLog.objects.filter(workspace=self.workspace, action="workspace.onboarding.completed").first()
		self.assertIsNotNone(audit)
		self.assertEqual(audit.actor, self.owner)
		self.assertEqual(audit.target_type, "workspace")
