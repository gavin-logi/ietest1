# 变更记录: 20261126-0902 新增：SSO 单元测试（用假 IdP 客户端覆盖成功、拒绝、错误与登出等分支）
import secrets
from unittest import mock

import requests
from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.test import Client, TestCase, override_settings
from joserfc.errors import BadSignatureError

from apps.accounts import sso

User = get_user_model()

ISSUER = "https://idp.example.com"
SSO_SETTINGS = {
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": secrets.token_urlsafe(16),
    "OIDC_REDIRECT_URI": "http://testserver/api/auth/callback/",
    "OIDC_USER_KEY_CLAIM": "employeeNumber",
    "OIDC_CREATE_USERS": True,
    "OIDC_POST_LOGOUT_REDIRECT_URI": "http://testserver/",
    "OIDC_LOGOUT_FROM_IDP": True,
}


def claims(**extra):
    base = {
        "sub": "00u-abc",
        "employeeNumber": "10086",
        "email": "zhangsan@example.com",
        "given_name": "San",
        "family_name": "Zhang",
    }
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


class FakeClient:
    """模拟 Authlib 客户端：只实现视图用到的方法。"""

    def __init__(self, id_claims=None, userinfo=None, exc=None, metadata=None):
        self.id_claims = claims() if id_claims is None else id_claims
        self.userinfo_data = self.id_claims if userinfo is None else userinfo
        self.exc = exc
        self.metadata = metadata or {
            "issuer": ISSUER,
            "end_session_endpoint": f"{ISSUER}/logout",
        }
        self.redirect_uri = None

    def load_server_metadata(self):
        if isinstance(self.exc, requests.RequestException):
            raise self.exc
        return self.metadata

    def authorize_redirect(self, request, redirect_uri):
        self.redirect_uri = redirect_uri
        return HttpResponseRedirect(f"{ISSUER}/authorize?state=s")

    def authorize_access_token(self, request):
        if self.exc:
            raise self.exc
        return {
            "access_token": "at",
            "id_token": "header.payload.sig",
            "userinfo": self.id_claims,
        }

    def userinfo(self, token):
        return self.userinfo_data

    def create_logout_url(self, post_logout_redirect_uri=None, id_token_hint=None):
        return {
            "url": f"{ISSUER}/logout?id_token_hint={id_token_hint}"
            f"&post_logout_redirect_uri={post_logout_redirect_uri}"
        }


@override_settings(**SSO_SETTINGS)
class SsoTestCase(TestCase):
    def use_client(self, fake):
        patcher = mock.patch.object(sso, "get_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def callback(self, fake=None, query="?code=c&state=s"):
        self.use_client(fake or FakeClient())
        return self.client.get(f"/api/auth/callback/{query}")

    def assert_denied(self, response, reason, captured):
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "登录失败", status_code=403)
        self.assertEqual(captured.records[0].reason, f"sso:{reason}")
        self.assertEqual(captured.records[0].path, "/api/auth/callback/")


class DisabledTests(TestCase):
    @override_settings(OIDC_ISSUER="")
    def test_login_and_callback_return_503_when_not_configured(self):
        self.assertEqual(self.client.get("/api/auth/login/").status_code, 503)
        self.assertEqual(self.client.get("/api/auth/callback/").status_code, 503)


class LoginTests(SsoTestCase):
    def test_redirects_to_idp_with_configured_redirect_uri(self):
        fake = self.use_client(FakeClient())
        response = self.client.get("/api/auth/login/?next=/orders/42?tab=1")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(f"{ISSUER}/authorize"))
        self.assertEqual(fake.redirect_uri, SSO_SETTINGS["OIDC_REDIRECT_URI"])
        self.assertEqual(self.client.session[sso.SESSION_NEXT_KEY], "/orders/42?tab=1")

    def test_rejects_external_and_loop_next(self):
        self.use_client(FakeClient())
        for value in ("https://evil.example/", "//evil.example/", "/api/auth/login/"):
            self.client.get("/api/auth/login/", {"next": value})
            self.assertEqual(self.client.session[sso.SESSION_NEXT_KEY], "/", value)

    def test_issuer_mismatch_is_configuration_error(self):
        self.use_client(FakeClient(metadata={"issuer": "https://other.example.com"}))
        with self.assertLogs("accounts.sso", level="ERROR"):
            response = self.client.get("/api/auth/login/")
        self.assertEqual(response.status_code, 500)

    def test_idp_unreachable_returns_502(self):
        self.use_client(FakeClient(exc=requests.ConnectionError("down")))
        with self.assertLogs("accounts.sso", level="ERROR"):
            response = self.client.get("/api/auth/login/")
        self.assertEqual(response.status_code, 502)


class CallbackSuccessTests(SsoTestCase):
    def test_first_login_creates_user_and_audits(self):
        session = self.client.session
        session[sso.SESSION_NEXT_KEY] = "/orders/42"
        session.save()
        # 顺序：assertLogs 在外层，on_commit 回调在内层退出时执行
        with (
            self.assertLogs("audit", level="INFO") as audit,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.callback()
        self.assertRedirects(response, "/orders/42", fetch_redirect_response=False)

        user = User.objects.get(employee_number="10086")
        self.assertEqual(user.username, "10086")
        self.assertEqual(user.email, "zhangsan@example.com")
        self.assertEqual((user.first_name, user.last_name), ("San", "Zhang"))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(
            self.client.session[sso.SESSION_ID_TOKEN_KEY], "header.payload.sig"
        )

        record = audit.records[0]
        self.assertEqual(record.action, "CREATE")
        self.assertEqual(record.resource, {"type": "user", "id": str(user.pk)})
        self.assertEqual(record.changes["employee_number"], "10086")
        self.assertEqual(record.changes["email"], sso.REDACTED_PII)
        self.assertNotIn("zhangsan@example.com", str(record.changes))
        # 登录后 operator 为该用户本人
        self.assertEqual(record.operator["username"], "10086")

    def test_existing_user_profile_sync_is_audited_without_pii(self):
        user = User.objects.create_user(
            username="10086", employee_number="10086", email="old@example.com"
        )
        # 顺序：assertLogs 在外层，on_commit 回调在内层退出时执行
        with (
            self.assertLogs("audit", level="INFO") as audit,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.callback()
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.email, "zhangsan@example.com")
        self.assertEqual(audit.records[0].action, "UPDATE")
        self.assertEqual(audit.records[0].changes["email"], sso.REDACTED_PII)
        self.assertNotIn("old@example.com", str(audit.records[0].changes))

    def test_unchanged_profile_writes_no_audit(self):
        User.objects.create_user(
            username="10086",
            employee_number="10086",
            email="zhangsan@example.com",
            first_name="San",
            last_name="Zhang",
        )
        with self.assertNoLogs("audit"), self.captureOnCommitCallbacks(execute=True):
            response = self.callback()
        self.assertEqual(response.status_code, 302)

    def test_employee_number_from_userinfo_only(self):
        # Okta 的自定义 claim 可能只出现在 userinfo 中
        fake = FakeClient(id_claims=claims(employeeNumber=None), userinfo=claims())
        response = self.callback(fake)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(employee_number="10086").exists())

    def test_numeric_claim_is_accepted(self):
        response = self.callback(FakeClient(id_claims=claims(employeeNumber=10086)))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(employee_number="10086").exists())

    def test_login_success_is_logged(self):
        with self.assertLogs("accounts.sso", level="INFO") as captured:
            self.callback()
        self.assertEqual(captured.records[-1].event, "login")


class CallbackDeniedTests(SsoTestCase):
    def test_idp_access_denied(self):
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(query="?error=access_denied&state=s")
        self.assert_denied(response, "idp_error:access_denied", captured)
        self.assertContains(response, "没有本应用的访问权限", status_code=403)

    def test_missing_employee_number_claim(self):
        fake = FakeClient(id_claims=claims(employeeNumber=None))
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(fake)
        self.assert_denied(response, "missing_claim:employeeNumber", captured)
        self.assertContains(response, "employeeNumber", status_code=403)
        self.assertFalse(User.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_state_mismatch(self):
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(FakeClient(exc=MismatchingStateError()))
        self.assert_denied(response, "state_mismatch", captured)

    def test_token_endpoint_error(self):
        fake = FakeClient(exc=OAuthError(error="invalid_grant"))
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(fake)
        self.assert_denied(response, "oauth_error:invalid_grant", captured)

    def test_invalid_id_token_signature(self):
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(FakeClient(exc=BadSignatureError()))
        self.assert_denied(response, "invalid_id_token:BadSignatureError", captured)

    def test_unvalidated_id_token_is_rejected(self):
        fake = FakeClient()
        fake.authorize_access_token = lambda request: {"access_token": "at"}
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(fake)
        self.assert_denied(response, "id_token_not_validated", captured)

    def test_userinfo_sub_mismatch(self):
        fake = FakeClient(userinfo=claims(sub="someone-else"))
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback(fake)
        self.assert_denied(response, "userinfo_sub_mismatch", captured)

    def test_inactive_user(self):
        User.objects.create_user(
            username="10086", employee_number="10086", is_active=False
        )
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback()
        self.assert_denied(response, "user_inactive", captured)

    @override_settings(OIDC_CREATE_USERS=False)
    def test_unknown_user_when_auto_create_disabled(self):
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback()
        self.assert_denied(response, "user_not_provisioned", captured)
        self.assertFalse(User.objects.exists())

    def test_username_conflict_with_local_account(self):
        User.objects.create_user(username="10086")
        with self.assertLogs("security", level="WARNING") as captured:
            response = self.callback()
        self.assert_denied(response, "username_conflict", captured)

    def test_idp_unreachable_during_callback(self):
        fake = FakeClient()
        fake.userinfo = mock.Mock(side_effect=requests.Timeout("slow"))
        with self.assertLogs("accounts.sso", level="ERROR"):
            response = self.callback(fake)
        self.assertEqual(response.status_code, 502)


class LogoutTests(SsoTestCase):
    def login_via_sso(self):
        self.callback()
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_redirects_to_idp_with_id_token_hint(self):
        self.login_via_sso()
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{ISSUER}/logout", response["Location"])
        self.assertIn("id_token_hint=header.payload.sig", response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_json_for_spa(self):
        self.login_via_sso()
        response = self.client.post(
            "/api/auth/logout/", headers={"Accept": "application/json"}
        )
        self.assertIn(f"{ISSUER}/logout", response.json()["redirect_url"])

    @override_settings(OIDC_LOGOUT_FROM_IDP=False)
    def test_local_only_logout(self):
        self.login_via_sso()
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response["Location"], "http://testserver/")

    def test_logout_without_id_token_stays_local(self):
        user = User.objects.create_user(username="admin")
        self.client.force_login(user)
        self.use_client(FakeClient())
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response["Location"], "http://testserver/")

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get("/api/auth/logout/").status_code, 405)

    def test_logout_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        with self.assertLogs("security", level="WARNING"):
            response = client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 403)


class MeTests(TestCase):
    def test_anonymous(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["authenticated"], False)
        self.assertEqual(response.json()["login_url"], "/api/auth/login/")
        self.assertIn("csrftoken", response.cookies)

    def test_authenticated(self):
        user = User.objects.create_user(
            username="10086", employee_number="10086", email="a@example.com"
        )
        self.client.force_login(user)
        data = self.client.get("/api/auth/me/").json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["employee_number"], "10086")
