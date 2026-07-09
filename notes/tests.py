from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from allauth.account.models import EmailAddress
from billing.models import Subscription
from billing.services import transition_subscription_state
from common.models import AuditLog
from memberships.services import add_member
from notes.models import Note
from notes.services import create_note, delete_note, update_note
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


class NotesEndpointTests(TestCase):
	def setUp(self):
		self.owner_a = User.objects.create_user(username="owner_a_notes", password="pass123")
		self.owner_b = User.objects.create_user(username="owner_b_notes", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_notes", password="pass123")
		mark_verified(self.owner_a)
		mark_verified(self.owner_b)
		mark_verified(self.viewer)

		self.workspace_a = create_workspace(actor=self.owner_a, payload={"name": "Workspace Notes A"})
		self.workspace_b = create_workspace(actor=self.owner_b, payload={"name": "Workspace Notes B"})
		add_member(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"user": self.viewer, "role": "viewer"},
		)

	def test_owner_can_create_list_update_delete_note(self):
		self.client.force_login(self.owner_a)

		created = self.client.post(
			f"/w/{self.workspace_a.slug}/notes/",
			data={"title": "First Note", "body": "Body"},
			content_type="application/json",
		)
		self.assertEqual(created.status_code, 201)
		note_id = created.json()["id"]

		listed = self.client.get(f"/w/{self.workspace_a.slug}/notes/")
		self.assertEqual(listed.status_code, 200)
		self.assertEqual(len(listed.json()["items"]), 1)

		updated = self.client.patch(
			f"/w/{self.workspace_a.slug}/notes/{note_id}/",
			data={"title": "Updated"},
			content_type="application/json",
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.json()["title"], "Updated")

		deleted = self.client.delete(f"/w/{self.workspace_a.slug}/notes/{note_id}/")
		self.assertEqual(deleted.status_code, 204)
		self.assertEqual(Note.objects.filter(workspace=self.workspace_a).count(), 0)

	def test_viewer_can_view_but_cannot_create(self):
		create_note(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"title": "Shared", "body": "Visible"},
		)

		self.client.force_login(self.viewer)
		listed = self.client.get(f"/w/{self.workspace_a.slug}/notes/")
		self.assertEqual(listed.status_code, 200)

		denied = self.client.post(
			f"/w/{self.workspace_a.slug}/notes/",
			data={"title": "Nope", "body": "Denied"},
			content_type="application/json",
		)
		self.assertEqual(denied.status_code, 403)

	def test_cross_workspace_note_access_denied(self):
		note_b = create_note(
			actor=self.owner_b,
			workspace=self.workspace_b,
			payload={"title": "B Note", "body": "Only B"},
		)

		self.client.force_login(self.owner_a)
		response = self.client.get(f"/w/{self.workspace_a.slug}/notes/{note_b.id}/")
		self.assertEqual(response.status_code, 404)

	def test_notes_endpoint_returns_standardized_error(self):
		self.client.force_login(self.owner_a)
		response = self.client.post(
			f"/w/{self.workspace_a.slug}/notes/",
			data={"body": "Missing title"},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], "validation_error")

	def test_notes_write_blocked_by_feature_gate(self):
		transition_subscription_state(
			subscription=self.workspace_a.subscription,
			new_state=Subscription.State.CANCELED,
		)

		self.client.force_login(self.owner_a)
		response = self.client.post(
			f"/w/{self.workspace_a.slug}/notes/",
			data={"title": "Blocked", "body": "No"},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json()["error"]["code"], "permission_denied")

	def test_note_write_operations_create_audit_logs(self):
		note = create_note(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"title": "Audit", "body": "A"},
		)
		self.assertTrue(AuditLog.objects.filter(action="note.created", target_id=str(note.id)).exists())

		note = update_note(
			actor=self.owner_a,
			workspace=self.workspace_a,
			note=note,
			payload={"title": "Audit v2", "body": "B"},
		)
		self.assertTrue(AuditLog.objects.filter(action="note.updated", target_id=str(note.id)).exists())

		note_id = str(note.id)
		delete_note(actor=self.owner_a, workspace=self.workspace_a, note=note)
		self.assertTrue(AuditLog.objects.filter(action="note.deleted", target_id=note_id).exists())

	def test_notes_page_post_redirects_with_namespace(self):
		self.client.force_login(self.owner_a)
		response = self.client.post(
			f"/w/{self.workspace_a.slug}/notes/ui/",
			data={"title": "UI Note", "body": "Created via form"},
		)
		self.assertEqual(response.status_code, 302)
		expected = reverse("workspaces:notes:page", kwargs={"workspace_slug": self.workspace_a.slug})
		self.assertEqual(response["Location"], expected)
