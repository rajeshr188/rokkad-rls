import uuid
from unittest import SkipTest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db import DatabaseError
from django.test import TransactionTestCase

from billing.services import ensure_workspace_subscription
from core.db import apply_workspace_context
from memberships.models import WorkspaceMember
from notes.models import Note
from workspaces.models import Workspace


User = get_user_model()


class WorkspaceMemberRLSPostgresTests(TransactionTestCase):
    """PostgreSQL-only RLS integration tests for tenant isolation."""

    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def setUp(self):
        self.owner_a = User.objects.create_user(username="owner_a", password="pass123")
        self.owner_b = User.objects.create_user(username="owner_b", password="pass123")
        self.user_a = User.objects.create_user(username="user_a", password="pass123")
        self.user_b = User.objects.create_user(username="user_b", password="pass123")

        self.workspace_a = Workspace.objects.create(name="Workspace A", slug="workspace-a", owner=self.owner_a)
        self.workspace_b = Workspace.objects.create(name="Workspace B", slug="workspace-b", owner=self.owner_b)

        apply_workspace_context(self.workspace_a.id)
        WorkspaceMember.objects.create(
            workspace=self.workspace_a,
            user=self.user_a,
            role=WorkspaceMember.Role.STAFF,
            status=WorkspaceMember.Status.ACTIVE,
        )
        apply_workspace_context(self.workspace_b.id)
        WorkspaceMember.objects.create(
            workspace=self.workspace_b,
            user=self.user_b,
            role=WorkspaceMember.Role.STAFF,
            status=WorkspaceMember.Status.ACTIVE,
        )

    def _set_workspace_context(self, workspace_id):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            # false = keep this value for the current DB session so ORM queries see it.
            cursor.execute("SELECT set_config(%s, %s, false)", [setting_name, str(workspace_id)])

    def _clear_workspace_context(self):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            cursor.execute(f"RESET {setting_name}")

    def _set_actor_context(self, actor_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, false)", ["app.current_actor_id", str(actor_id)])

    def test_rls_allows_only_current_workspace_rows(self):
        self._set_workspace_context(self.workspace_a.id)
        workspace_ids_a = set(WorkspaceMember.objects.values_list("workspace_id", flat=True))
        self.assertEqual(workspace_ids_a, {self.workspace_a.id})

        self._set_workspace_context(self.workspace_b.id)
        workspace_ids_b = set(WorkspaceMember.objects.values_list("workspace_id", flat=True))
        self.assertEqual(workspace_ids_b, {self.workspace_b.id})

    def test_rls_denies_rows_for_unknown_workspace_context(self):
        self._set_workspace_context(uuid.uuid4())
        self.assertEqual(WorkspaceMember.objects.count(), 0)

    def test_rls_denies_rows_when_workspace_context_missing(self):
        self._clear_workspace_context()
        self.assertEqual(WorkspaceMember.objects.count(), 0)

    def test_self_read_policy_allows_actor_rows_without_cross_user_leak(self):
        self._clear_workspace_context()
        self._set_actor_context(self.user_b.id)
        rows = list(WorkspaceMember.objects.values_list("workspace_id", "user_id"))
        self.assertEqual(rows, [(self.workspace_b.id, self.user_b.id)])


class TenantTableRLSPostgresTests(TransactionTestCase):
    """PostgreSQL-only RLS tests expanded to note and subscription tenant tables."""

    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def setUp(self):
        self.owner_a = User.objects.create_user(username="tenant_owner_a", password="pass123")
        self.owner_b = User.objects.create_user(username="tenant_owner_b", password="pass123")

        self.workspace_a = Workspace.objects.create(name="Tenant Workspace A", slug="tenant-workspace-a", owner=self.owner_a)
        self.workspace_b = Workspace.objects.create(name="Tenant Workspace B", slug="tenant-workspace-b", owner=self.owner_b)

        apply_workspace_context(self.workspace_a.id)
        Note.objects.create(workspace=self.workspace_a, created_by=self.owner_a, title="A1", body="alpha")
        ensure_workspace_subscription(workspace=self.workspace_a)

        apply_workspace_context(self.workspace_b.id)
        Note.objects.create(workspace=self.workspace_b, created_by=self.owner_b, title="B1", body="beta")
        ensure_workspace_subscription(workspace=self.workspace_b)

    def _set_workspace_context(self, workspace_id):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, false)", [setting_name, str(workspace_id)])

    def _clear_workspace_context(self):
        setting_name = getattr(settings, "RLS_WORKSPACE_SETTING", "app.current_workspace_id")
        with connection.cursor() as cursor:
            cursor.execute(f"RESET {setting_name}")

    def test_note_rls_isolation_by_workspace(self):
        self._set_workspace_context(self.workspace_a.id)
        note_workspace_ids = set(Note.objects.values_list("workspace_id", flat=True))
        self.assertEqual(note_workspace_ids, {self.workspace_a.id})

        self._set_workspace_context(self.workspace_b.id)
        note_workspace_ids = set(Note.objects.values_list("workspace_id", flat=True))
        self.assertEqual(note_workspace_ids, {self.workspace_b.id})

    def test_subscription_rls_isolation_by_workspace(self):
        from billing.models import Subscription

        self._set_workspace_context(self.workspace_a.id)
        subscription_workspace_ids = set(Subscription.objects.values_list("workspace_id", flat=True))
        self.assertEqual(subscription_workspace_ids, {self.workspace_a.id})

        self._set_workspace_context(self.workspace_b.id)
        subscription_workspace_ids = set(Subscription.objects.values_list("workspace_id", flat=True))
        self.assertEqual(subscription_workspace_ids, {self.workspace_b.id})

    def test_unknown_workspace_context_blocks_notes_and_subscriptions(self):
        from billing.models import Subscription

        self._set_workspace_context(uuid.uuid4())
        self.assertEqual(Note.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 0)

    def test_missing_workspace_context_blocks_notes_and_subscriptions(self):
        from billing.models import Subscription

        self._clear_workspace_context()
        self.assertEqual(Note.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 0)

    def test_insert_into_another_workspace_fails_under_rls(self):
        self._set_workspace_context(self.workspace_a.id)
        with self.assertRaises(DatabaseError):
            Note.objects.create(
                workspace=self.workspace_b,
                created_by=self.owner_a,
                title="cross-workspace-insert",
                body="should fail",
            )

    def test_update_that_moves_workspace_fails_under_rls(self):
        self._set_workspace_context(self.workspace_a.id)
        note = Note.objects.get(workspace=self.workspace_a)
        note.workspace = self.workspace_b

        with self.assertRaises(DatabaseError):
            note.save(update_fields=["workspace"])

    def test_raw_sql_without_workspace_filter_is_rls_protected(self):
        self._set_workspace_context(self.workspace_a.id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT workspace_id FROM notes_note")
            rows = cursor.fetchall()

        workspace_ids = {row[0] for row in rows}
        self.assertEqual(workspace_ids, {self.workspace_a.id})

        self._clear_workspace_context()
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM notes_note")
            count_without_context = cursor.fetchone()[0]

        self.assertEqual(count_without_context, 0)


class RuntimeRoleRLSPostgresTests(TransactionTestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise SkipTest("PostgreSQL-only test class.")

    def test_current_runtime_role_does_not_have_bypassrls(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            role_name, bypass_rls = cursor.fetchone()

        self.assertFalse(
            bypass_rls,
            msg=f"Runtime role {role_name} unexpectedly has BYPASSRLS.",
        )
