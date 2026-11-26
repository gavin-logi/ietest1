# 变更记录: 20261126-0902 新增：SSO 端到端测试，对接真实运行的 mock-idp（未设置 SSO_E2E_ISSUER 时跳过）
# 变更记录: 20261126-1333 默认指向本机 mock-idp（http://localhost:8090/default，可由 SSO_E2E_ISSUER 覆盖）；mock-idp 未运行时跳过，不再需要手动设置环境变量
"""端到端测试：真实的 Django 服务 + 真实的 mock-idp，验证签名、nonce、PKCE、userinfo、登出整条链路。

运行方式（在仓库根目录先启动 mock-idp）：
    docker compose up -d mock-idp
    cd backend
    DATABASE_URL=sqlite://:memory: uv run --python 3.12 python manage.py test apps.accounts.tests.test_sso_e2e
"""

import os
import secrets
import unittest
from urllib.parse import parse_qs, urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from apps.accounts import sso

E2E_ISSUER = os.environ.get("SSO_E2E_ISSUER", "http://localhost:8090/default").rstrip(
    "/"
)


def _mock_idp_reachable():
    """mock-idp 未运行时返回 False，测试跳过而不是失败。"""
    try:
        response = requests.get(
            f"{E2E_ISSUER}/.well-known/openid-configuration", timeout=1
        )
    except requests.RequestException:
        return False
    return response.status_code == 200


class SsoEndToEndTests(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if not _mock_idp_reachable():
            raise unittest.SkipTest(f"模拟 IdP 不可达（{E2E_ISSUER}），跳过端到端测试")
        super().setUpClass()

    def setUp(self):
        sso._clients.clear()
        overrides = override_settings(
            OIDC_ISSUER=E2E_ISSUER,
            OIDC_CLIENT_ID="local-client",
            OIDC_CLIENT_SECRET=secrets.token_urlsafe(16),
            OIDC_REDIRECT_URI=f"{self.live_server_url}/api/auth/callback/",
            OIDC_POST_LOGOUT_REDIRECT_URI=f"{self.live_server_url}/",
            OIDC_CREATE_USERS=True,
            OIDC_LOGOUT_FROM_IDP=True,
        )
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.http = requests.Session()

    def sign_in(self, username, next_path="/after-login"):
        """模拟浏览器：访问登录 → 跳到 mock-idp 登录页 → 提交用户名 → 回调 → 跳回 next。"""
        page = self.http.get(
            f"{self.live_server_url}/api/auth/login/", params={"next": next_path}
        )
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.url.startswith(E2E_ISSUER), page.url)
        query = parse_qs(urlparse(page.url).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("nonce", query)
        return self.http.post(page.url, data={"username": username, "claims": ""})

    def test_full_login_and_logout(self):
        response = self.sign_in("10086")
        # 回调成功后跳回 next（未构建前端时 SPA 兜底返回 404，这里只检查跳转链）
        self.assertEqual(urlparse(response.url).path, "/after-login")
        callback = [r for r in response.history if "/api/auth/callback/" in r.url]
        self.assertEqual(len(callback), 1)
        self.assertEqual(callback[0].status_code, 302)

        me = self.http.get(f"{self.live_server_url}/api/auth/me/").json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["employee_number"], "10086")
        self.assertEqual(me["user"]["email"], "user10086@example.com")
        user = get_user_model().objects.get(employee_number="10086")
        self.assertEqual(user.username, "10086")

        logout = self.http.post(
            f"{self.live_server_url}/api/auth/logout/",
            headers={
                "Accept": "application/json",
                "X-CSRFToken": self.http.cookies["csrftoken"],
                "Referer": f"{self.live_server_url}/",
            },
        )
        self.assertEqual(logout.status_code, 200)
        redirect_url = logout.json()["redirect_url"]
        self.assertTrue(redirect_url.startswith(f"{E2E_ISSUER}/endsession"))
        self.assertIn("id_token_hint=", redirect_url)
        me = self.http.get(f"{self.live_server_url}/api/auth/me/").json()
        self.assertFalse(me["authenticated"])

    def test_missing_employee_number_is_denied(self):
        response = self.sign_in("no-employee-number")
        self.assertEqual(response.status_code, 403)
        self.assertIn("employeeNumber", response.text)
        self.assertFalse(get_user_model().objects.exists())

    def test_replayed_callback_is_rejected(self):
        response = self.sign_in("10087")
        callback_url = next(
            r.url for r in response.history if "/api/auth/callback/" in r.url
        )
        # 同一个回调链接再次使用：state 已被清除，必须拒绝
        replay = self.http.get(callback_url)
        self.assertEqual(replay.status_code, 403)
