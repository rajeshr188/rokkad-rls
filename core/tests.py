import importlib
from unittest.mock import MagicMock, patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.middleware import RLSContextMiddleware, RequestRateLimitMiddleware, WorkspaceContextMiddleware
from core.db import rls
from memberships.models import WorkspaceMember
from workspaces.services import create_workspace


User = get_user_model()


def mark_verified(user):
	EmailAddress.objects.update_or_create(
		user=user,
		email=f"{user.username}@example.com",
		defaults={"verified": True, "primary": True},
	)


def _dummy_view(request):
	return None


class WorkspaceContextMiddlewareTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.middleware = WorkspaceContextMiddleware(get_response=lambda request: None)

		self.user = User.objects.create_user(username="member", password="pass123")
		self.non_member = User.objects.create_user(username="other", password="pass123")
		mark_verified(self.user)
		mark_verified(self.non_member)
		self.workspace = create_workspace(actor=self.user, payload={"name": "Acme"})

	def test_process_view_skips_when_workspace_slug_missing(self):
		request = self.factory.get("/")
		request.user = self.user

		result = self.middleware.process_view(request, _dummy_view, (), {})

		self.assertIsNone(result)
		self.assertIsNone(request.active_workspace)

	def test_process_view_rejects_unauthenticated_workspace_route(self):
		request = self.factory.get(f"/w/{self.workspace.slug}/")
		request.user = AnonymousUser()

		with self.assertRaises(PermissionDenied):
			self.middleware.process_view(
				request,
				_dummy_view,
				(),
				{"workspace_slug": self.workspace.slug},
			)

	def test_process_view_sets_active_workspace_for_member(self):
		request = self.factory.get(f"/w/{self.workspace.slug}/")
		request.user = self.user

		self.middleware.process_view(
			request,
			_dummy_view,
			(),
			{"workspace_slug": self.workspace.slug},
		)

		self.assertEqual(request.active_workspace, self.workspace)

	def test_process_view_rejects_non_member(self):
		request = self.factory.get(f"/w/{self.workspace.slug}/")
		request.user = self.non_member

		with self.assertRaises(PermissionDenied):
			self.middleware.process_view(
				request,
				_dummy_view,
				(),
				{"workspace_slug": self.workspace.slug},
			)


class RLSContextMiddlewareTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.middleware = RLSContextMiddleware(get_response=lambda request: None)

		self.user = User.objects.create_user(username="member2", password="pass123")
		self.workspace = create_workspace(actor=self.user, payload={"name": "Globex"})

	def test_process_view_skips_when_no_workspace(self):
		request = self.factory.get("/")
		request.user = self.user

		result = self.middleware.process_view(request, _dummy_view, (), {})
		self.assertIsNone(result)
		self.assertFalse(request.rls_context_applied)

	def test_process_view_skips_for_non_postgresql(self):
		request = self.factory.get("/")
		request.user = self.user
		request.active_workspace = self.workspace

		with patch("core.middleware.connection") as mock_connection:
			mock_connection.vendor = "sqlite"
			self.middleware.process_view(request, _dummy_view, (), {})
		self.assertFalse(request.rls_context_applied)

	@patch("core.middleware.connection")
	@patch("core.middleware.apply_actor_context")
	@patch("core.middleware.apply_workspace_context")
	def test_process_view_sets_db_setting_for_postgresql(self, mock_apply_context, mock_apply_actor_context, mock_connection):
		request = self.factory.get("/")
		request.user = self.user
		request.active_workspace = self.workspace

		mock_connection.vendor = "postgresql"
		mock_apply_context.return_value = True

		self.middleware.process_view(request, _dummy_view, (), {})

		self.assertTrue(request.rls_context_applied)
		mock_apply_actor_context.assert_called_once_with(self.user.id)
		mock_apply_context.assert_called_once_with(self.workspace.id)


class RLSSettingLocalBehaviorTests(TestCase):
	def _mock_cursor_connection(self, mock_connection):
		mock_cursor = MagicMock()
		context_manager = MagicMock()
		context_manager.__enter__.return_value = mock_cursor
		context_manager.__exit__.return_value = False
		mock_connection.cursor.return_value = context_manager
		mock_connection.vendor = "postgresql"
		return mock_cursor

	@override_settings(RLS_CONTEXT_LOCAL=True)
	@patch("core.db.rls.connection")
	def test_apply_workspace_context_does_not_use_local_outside_atomic(self, mock_connection):
		mock_connection.in_atomic_block = False
		mock_cursor = self._mock_cursor_connection(mock_connection)

		rls.apply_workspace_context("11111111-1111-1111-1111-111111111111")

		params = mock_cursor.execute.call_args.args[1]
		self.assertFalse(params[2])

	@override_settings(RLS_CONTEXT_LOCAL=True)
	@patch("core.db.rls.connection")
	def test_apply_workspace_context_uses_local_inside_atomic(self, mock_connection):
		mock_connection.in_atomic_block = True
		mock_cursor = self._mock_cursor_connection(mock_connection)

		rls.apply_workspace_context("22222222-2222-2222-2222-222222222222")

		params = mock_cursor.execute.call_args.args[1]
		self.assertTrue(params[2])

	@patch("core.db.rls.connection")
	def test_clear_workspace_context_uses_reset(self, mock_connection):
		mock_connection.in_atomic_block = False
		mock_cursor = self._mock_cursor_connection(mock_connection)

		rls.clear_workspace_context()

		self.assertEqual(mock_cursor.execute.call_args.args[0], "RESET app.current_workspace_id")


class RLSContextManagerTests(TestCase):
	@patch("core.db.rls.apply_workspace_context", return_value=True)
	@patch("core.db.rls.clear_workspace_context", return_value=True)
	def test_workspace_context_applies_and_clears(self, mock_clear, mock_apply):
		with rls.workspace_context("33333333-3333-3333-3333-333333333333") as applied:
			self.assertTrue(applied)

		mock_apply.assert_called_once_with("33333333-3333-3333-3333-333333333333", local=None)
		mock_clear.assert_called_once_with(local=None)

	@patch("core.db.rls.apply_workspace_context", return_value=True)
	@patch("core.db.rls.clear_workspace_context", return_value=True)
	def test_workspace_context_clears_on_exception(self, mock_clear, mock_apply):
		with self.assertRaisesRegex(RuntimeError, "boom"):
			with rls.workspace_context("44444444-4444-4444-4444-444444444444"):
				raise RuntimeError("boom")

		mock_apply.assert_called_once_with("44444444-4444-4444-4444-444444444444", local=None)
		mock_clear.assert_called_once_with(local=None)

	@patch("core.db.rls.apply_workspace_context", return_value=True)
	@patch("core.db.rls.clear_workspace_context", return_value=True)
	def test_workspace_context_does_not_clear_when_not_applied(self, mock_clear, mock_apply):
		mock_apply.return_value = False

		with rls.workspace_context(None) as applied:
			self.assertFalse(applied)

		mock_clear.assert_not_called()

	@patch("core.db.rls.apply_actor_context", return_value=True)
	@patch("core.db.rls.clear_actor_context", return_value=True)
	@patch("core.db.rls.apply_workspace_context", return_value=True)
	@patch("core.db.rls.clear_workspace_context", return_value=True)
	@patch("core.db.rls.apply_invitation_token_context", return_value=True)
	@patch("core.db.rls.clear_invitation_token_context", return_value=True)
	def test_tenant_context_applies_and_clears_all(
		self,
		mock_clear_invitation,
		mock_apply_invitation,
		mock_clear_workspace,
		mock_apply_workspace,
		mock_clear_actor,
		mock_apply_actor,
	):
		with rls.tenant_context(
			actor_id=10,
			workspace_id="55555555-5555-5555-5555-555555555555",
			invitation_token="invite-token",
		):
			pass

		mock_apply_actor.assert_called_once_with(10, local=None)
		mock_apply_workspace.assert_called_once_with("55555555-5555-5555-5555-555555555555", local=None)
		mock_apply_invitation.assert_called_once_with("invite-token", local=None)
		mock_clear_invitation.assert_called_once_with(local=None)
		mock_clear_workspace.assert_called_once_with(local=None)
		mock_clear_actor.assert_called_once_with(local=None)


class HealthEndpointTests(TestCase):
	def test_healthz_returns_ok(self):
		response = self.client.get(reverse("healthz"))
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["status"], "ok")
		self.assertTrue(payload["checks"]["database"]["ok"])


class SettingsImportSmokeTests(TestCase):
	def test_settings_modules_import_cleanly(self):
		base = importlib.import_module("config.settings.base")
		dev = importlib.import_module("config.settings.dev")
		postgres = importlib.import_module("config.settings.postgres")
		prod = importlib.import_module("config.settings.prod")

		self.assertTrue(hasattr(base, "INSTALLED_APPS"))
		self.assertTrue(hasattr(dev, "DEBUG"))
		self.assertTrue(hasattr(postgres, "DATABASES"))
		self.assertTrue(hasattr(prod, "SECURE_SSL_REDIRECT"))


@override_settings(
	RATE_LIMIT_ENABLED=True,
	RATE_LIMIT_WINDOW_SECONDS=60,
	RATE_LIMIT_LOGIN_MAX_REQUESTS=2,
	RATE_LIMIT_WRITE_MAX_REQUESTS=2,
)
class RequestRateLimitMiddlewareTests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.middleware = RequestRateLimitMiddleware(get_response=lambda request: None)

	def test_login_rate_limit_blocks_after_threshold(self):
		for _ in range(2):
			request = self.factory.post("/accounts/login/", HTTP_ACCEPT="application/json")
			request.META["REMOTE_ADDR"] = "127.0.0.10"
			response = self.middleware.process_request(request)
			self.assertIsNone(response)

		blocked = self.factory.post("/accounts/login/", HTTP_ACCEPT="application/json")
		blocked.META["REMOTE_ADDR"] = "127.0.0.10"
		blocked_response = self.middleware.process_request(blocked)
		self.assertIsNotNone(blocked_response)
		self.assertEqual(blocked_response.status_code, 429)

	def test_workspace_write_rate_limit_blocks_after_threshold(self):
		for _ in range(2):
			request = self.factory.post("/w/demo/notes/", HTTP_ACCEPT="application/json")
			request.META["REMOTE_ADDR"] = "127.0.0.20"
			response = self.middleware.process_request(request)
			self.assertIsNone(response)

		blocked = self.factory.post("/w/demo/notes/", HTTP_ACCEPT="application/json")
		blocked.META["REMOTE_ADDR"] = "127.0.0.20"
		blocked_response = self.middleware.process_request(blocked)
		self.assertIsNotNone(blocked_response)
		self.assertEqual(blocked_response.status_code, 429)
