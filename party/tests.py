from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.test import TestCase

from allauth.account.models import EmailAddress
from party.models import PartyAddress, PartyContactMethod, PartyDocument, PartyRole
from memberships.services import add_member
from party.services import create_party, delete_party, get_party, list_parties, update_party
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


class PartyServiceTests(TestCase):
	def setUp(self):
		self.owner_a = User.objects.create_user(username="owner_a_party", password="pass123")
		self.owner_b = User.objects.create_user(username="owner_b_party", password="pass123")
		self.viewer = User.objects.create_user(username="viewer_party", password="pass123")
		mark_verified(self.owner_a)
		mark_verified(self.owner_b)
		mark_verified(self.viewer)

		self.workspace_a = create_workspace(actor=self.owner_a, payload={"name": "Workspace Party A"})
		self.workspace_b = create_workspace(actor=self.owner_b, payload={"name": "Workspace Party B"})
		add_member(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"user": self.viewer, "role": "viewer"},
		)

	def test_owner_can_create_and_update_party(self):
		party = create_party(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={
				"name": "Sharma Traders",
				"party_type": "supplier",
				"roles": ["supplier", "wholesaler"],
				"contacts": [{"name": "Ravi", "phone": "9999999999"}],
				"addresses": [{"line1": "Main Road", "city": "Jaipur"}],
				"documents": [{"type": "gst", "value": "08ABCDE1234F1Z5"}],
			},
		)

		self.assertEqual(party.workspace_id, self.workspace_a.id)
		self.assertEqual(party.party_type, "supplier")
		self.assertEqual(PartyRole.objects.filter(workspace=self.workspace_a, party=party).count(), 2)
		self.assertEqual(PartyContactMethod.objects.filter(workspace=self.workspace_a, party=party).count(), 1)
		self.assertEqual(PartyAddress.objects.filter(workspace=self.workspace_a, party=party).count(), 1)
		self.assertEqual(PartyDocument.objects.filter(workspace=self.workspace_a, party=party).count(), 1)

		updated = update_party(
			actor=self.owner_a,
			workspace=self.workspace_a,
			party=party,
			payload={
				"name": "Sharma Traders LLP",
				"is_active": False,
				"contacts": [
					{
						"contact_type": "email",
						"value": "owner@sharmatraders.example",
						"is_primary": True,
					}
				],
			},
		)
		self.assertEqual(updated.name, "Sharma Traders LLP")
		self.assertFalse(updated.is_active)
		self.assertEqual(PartyContactMethod.objects.filter(workspace=self.workspace_a, party=party).count(), 1)
		self.assertEqual(updated.primary_email, "owner@sharmatraders.example")

	def test_viewer_can_list_but_cannot_create_party(self):
		create_party(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"name": "Retail One", "party_type": "retailer"},
		)

		parties = list_parties(actor=self.viewer, workspace=self.workspace_a)
		self.assertEqual(parties.count(), 1)

		with self.assertRaises(PermissionDenied):
			create_party(
				actor=self.viewer,
				workspace=self.workspace_a,
				payload={"name": "Nope", "party_type": "customer"},
			)

	def test_cross_workspace_party_access_is_denied(self):
		party_b = create_party(
			actor=self.owner_b,
			workspace=self.workspace_b,
			payload={"name": "B Party", "party_type": "customer"},
		)

		with self.assertRaises(ValidationError):
			get_party(actor=self.owner_a, workspace=self.workspace_a, party_id=party_b.id)

	def test_invalid_party_payload_is_rejected(self):
		with self.assertRaises(ValidationError):
			create_party(
				actor=self.owner_a,
				workspace=self.workspace_a,
				payload={"name": "", "party_type": "customer"},
			)

		with self.assertRaises(ValidationError):
			create_party(
				actor=self.owner_a,
				workspace=self.workspace_a,
				payload={"name": "Bad Type", "party_type": "invalid"},
			)

		with self.assertRaises(ValidationError):
			create_party(
				actor=self.owner_a,
				workspace=self.workspace_a,
				payload={"name": "Bad Contacts", "party_type": "customer", "contacts": {}},
			)

	def test_owner_can_delete_party(self):
		party = create_party(
			actor=self.owner_a,
			workspace=self.workspace_a,
			payload={"name": "To Delete", "party_type": "customer"},
		)

		delete_party(actor=self.owner_a, workspace=self.workspace_a, party=party)
		self.assertEqual(list_parties(actor=self.owner_a, workspace=self.workspace_a).count(), 0)
