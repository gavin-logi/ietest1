# 变更记录: 20261126-0902 新增：OIDC 客户端（Authlib，discovery + PKCE）、按 employeeNumber 识别或创建用户、登出地址
"""SSO 核心逻辑，与视图分离以便测试。

流程：login 跳转 IdP（state、nonce、PKCE 由 Authlib 生成并存入 session）→ IdP 回调 →
用 code 换 token 并校验 id_token（签名、iss、aud、exp、nonce）→ 读取 userinfo →
按 employeeNumber 找到或创建用户 → 建立 Django session。浏览器只持有 session cookie，不接触 token。
"""

import threading
from dataclasses import dataclass, field

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme

# Authlib 在 session 中保存 state 数据时使用的名字（键为 _state_oidc_<state>）
CLIENT_NAME = "oidc"
SESSION_NEXT_KEY = "sso_next"
SESSION_ID_TOKEN_KEY = "sso_id_token"
REDACTED_PII = "field_modified"

_clients = {}
_clients_lock = threading.Lock()


class SsoDenied(Exception):
    """登录被拒绝。reason 写入 SECURITY 日志（不含个人信息），message 展示给用户。"""

    def __init__(self, reason, message):
        super().__init__(reason)
        self.reason = reason
        self.message = message


class SsoConfigError(Exception):
    """IdP 配置与本地配置不一致（例如 discovery 返回的 issuer 不同）。"""


@dataclass
class LoginResult:
    user: object
    created: bool = False
    # 字段名 → {"before": ..., "after": ...}，用于审计日志
    changes: dict = field(default_factory=dict)


def sso_enabled():
    return bool(settings.OIDC_ISSUER)


def discovery_url():
    return settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"


def get_client():
    """返回 OIDC 客户端。按配置缓存，discovery 文档与 JWKS 在进程内只获取一次（签名密钥轮换时自动重新获取）。"""
    key = (
        settings.OIDC_ISSUER,
        settings.OIDC_CLIENT_ID,
        settings.OIDC_CLIENT_SECRET,
        settings.OIDC_SCOPES,
        settings.OIDC_HTTP_TIMEOUT,
    )
    with _clients_lock:
        client = _clients.get(key)
        if client is None:
            oauth = OAuth()
            oauth.register(
                name=CLIENT_NAME,
                client_id=settings.OIDC_CLIENT_ID,
                client_secret=settings.OIDC_CLIENT_SECRET,
                server_metadata_url=discovery_url(),
                client_kwargs={
                    "scope": settings.OIDC_SCOPES,
                    "code_challenge_method": "S256",
                    "default_timeout": settings.OIDC_HTTP_TIMEOUT,
                },
            )
            client = oauth.create_client(CLIENT_NAME)
            _clients[key] = client
        return client


def check_issuer(client):
    """discovery 返回的 issuer 必须与配置一致（OIDC 规范要求），否则 id_token 的 iss 校验没有意义。"""
    issuer = client.load_server_metadata().get("issuer", "")
    if issuer.rstrip("/") != settings.OIDC_ISSUER.rstrip("/"):
        raise SsoConfigError(
            f"discovery issuer {issuer!r} 与 OIDC_ISSUER {settings.OIDC_ISSUER!r} 不一致"
        )


def safe_next(request, value):
    """只允许跳回本站的相对路径，防止开放重定向；指向认证端点时回到首页，避免循环。"""
    if (
        value
        and value.startswith("/")
        and not value.startswith("//")
        and not value.startswith("/api/auth/")
        and url_has_allowed_host_and_scheme(
            value,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return value
    return "/"


def merge_claims(id_token_claims, userinfo):
    """合并 id_token 与 userinfo 的 claim。

    Okta 的自定义 claim（如 employeeNumber）可能只出现在 userinfo 中，因此两者都要读取。
    OIDC 规范要求 userinfo 的 sub 与 id_token 一致，不一致说明响应被篡改或串号，必须拒绝。
    """
    claims = dict(id_token_claims)
    if userinfo:
        if userinfo.get("sub") != id_token_claims.get("sub"):
            raise SsoDenied("userinfo_sub_mismatch", "身份信息校验失败，请重新登录。")
        claims.update(userinfo)
    return claims


def _claim_str(claims, name, max_length):
    value = claims.get(name)
    if value is None:
        return ""
    value = str(value).strip()
    return value if len(value) <= max_length else ""


def resolve_user(claims):
    """按 employeeNumber 找到或创建用户，并同步 email 与姓名。

    返回 LoginResult；不满足登录条件时抛出 SsoDenied。数据库写入在事务中完成，调用方在事务提交后记录审计日志。
    """
    user_model = get_user_model()
    key_claim = settings.OIDC_USER_KEY_CLAIM
    employee_number = _claim_str(
        claims, key_claim, user_model._meta.get_field("employee_number").max_length
    )
    if not employee_number:
        raise SsoDenied(
            f"missing_claim:{key_claim}",
            f"身份提供方未返回 {key_claim}，无法识别您的账号。"
            f"请联系 Okta 管理员为本应用配置 {key_claim} claim（preprod 与 prod 都需要配置）。",
        )

    profile = {
        "email": _claim_str(claims, "email", 254),
        "first_name": _claim_str(claims, "given_name", 150),
        "last_name": _claim_str(claims, "family_name", 150),
    }

    with transaction.atomic():
        user = (
            user_model.objects.select_for_update()
            .filter(employee_number=employee_number)
            .first()
        )
        if user is None:
            if not settings.OIDC_CREATE_USERS:
                raise SsoDenied(
                    "user_not_provisioned",
                    "您的账号尚未在本系统开通，请联系系统管理员。",
                )
            # 用户名使用工号：唯一、稳定，日志中的 operator.username 即为工号
            if user_model.objects.filter(username=employee_number).exists():
                raise SsoDenied(
                    "username_conflict",
                    "已存在同名的本地账号，无法自动开通，请联系系统管理员。",
                )
            user = user_model(
                username=employee_number,
                employee_number=employee_number,
                **{name: value for name, value in profile.items() if value},
            )
            # SSO 用户不能用密码登录
            user.set_unusable_password()
            user.save()
            return LoginResult(user=user, created=True)

        if not user.is_active:
            raise SsoDenied("user_inactive", "您的账号已停用，请联系系统管理员。")

        changes = {}
        for name, value in profile.items():
            # IdP 未提供的字段不覆盖本地值
            if value and getattr(user, name) != value:
                changes[name] = {"before": getattr(user, name), "after": value}
                setattr(user, name, value)
        if changes:
            user.save(update_fields=list(changes))
        return LoginResult(user=user, changes=changes)


def audit_changes(result):
    """审计日志中的 changes：工号与用户名记录原值；email 与姓名属于个人信息，只标注已修改。"""
    if result.created:
        user = result.user
        return {
            "username": user.username,
            "employee_number": user.employee_number,
            "email": REDACTED_PII if user.email else "",
            "source": "sso",
        }
    return {name: REDACTED_PII for name in result.changes}


def logout_url(client, id_token):
    """IdP 的 end-session 地址（带 id_token_hint，Okta 要求）。不支持或无 id_token 时返回 None。"""
    if not id_token:
        return None
    metadata = client.load_server_metadata()
    if not metadata.get("end_session_endpoint"):
        return None
    result = client.create_logout_url(
        post_logout_redirect_uri=settings.OIDC_POST_LOGOUT_REDIRECT_URI or None,
        id_token_hint=id_token,
    )
    return result["url"]
