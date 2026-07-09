import uuid
from unittest import SkipTest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db import DatabaseError
from django.test import TransactionTestCase

from core.db import apply_workspace_context
from party.models import Party
from workspaces.models import Workspace


User = get_user_model()


class PartyRLSPostgresTests(TransactionTestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def setUp(self):
        self.owner_a = User.objects.create_user(username="party_owner_a", password="pass123")
        self.owner_b = User.objects.create_user(username="party_owner_b", password="pass123")

        self.workspace_a = Workspace.objects.create(name="Party Workspace A", slug="party-workspace-a", owner=self.owner_a)
        self.workspace_b = Workspace.objects.create(name="Party Workspace B", slug="party-workspace-b", owner=self.owner_b)

        apply_workspace_context(self.workspace_a.id)
        Party.objects.create(workspace=self.workspace_a, created_by=self.owner_a, name="A Party", party_type="customer")

        apply_workspace_context(self.workspace_b.id)
        Party.objects.create(workspace=self.workspace_b, created_by=self.owner_b, name="B Party", party_type="supplier")

    def _set_workspace_context(self, workspace_id):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, false)", [setting_name, str(workspace_id)])

    def _clear_workspace_context(self):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            cursor.execute(f"RESET {setting_name}")

    def test_party_rls_isolation_by_workspace(self):
        self._set_workspace_context(self.workspace_a.id)
        workspace_ids = set(Party.objects.values_list("workspace_id", flat=True))
        self.assertEqual(workspace_ids, {self.workspace_a.id})

        self._set_workspace_context(self.workspace_b.id)
        workspace_ids = set(Party.objects.values_list("workspace_id", flat=True))
        self.assertEqual(workspace_ids, {self.workspace_b.id})

    def test_party_unknown_workspace_context_returns_zero_rows(self):
        self._set_workspace_context(uuid.uuid4())
        self.assertEqual(Party.objects.count(), 0)

    def test_party_missing_workspace_context_returns_zero_rows(self):
        self._clear_workspace_context()
        self.assertEqual(Party.objects.count(), 0)

    def test_party_insert_into_another_workspace_fails(self):
        self._set_workspace_context(self.workspace_a.id)
        with self.assertRaises(DatabaseError):
            Party.objects.create(
                workspace=self.workspace_b,
                created_by=self.owner_a,
                name="Cross Workspace",
                party_type="retailer",
            )

    def test_party_workspace_move_update_fails(self):
        self._set_workspace_context(self.workspace_a.id)
        party = Party.objects.get(workspace=self.workspace_a)
        party.workspace = self.workspace_b
        with self.assertRaises(DatabaseError):
            party.save(update_fields=["workspace"])

    def test_party_raw_sql_without_filter_is_rls_protected(self):
        self._set_workspace_context(self.workspace_a.id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT workspace_id FROM party_party")
            rows = cursor.fetchall()

        workspace_ids = {row[0] for row in rows}
        self.assertEqual(workspace_ids, {self.workspace_a.id})
