# 变更记录: 20261126-0902 新增：SSO 端点 login / callback / logout / me；拒绝时返回说明页并记录 SECURITY 日志
"""SSO 端点（挂在 /api/auth/ 下）。

- GET  /api/auth/login/?next=/path  跳转到 IdP
- GET  /api/auth/callback/          IdP 回调（即 Okta 的 Sign-in redirect URI）
- POST /api/auth/logout/            结束本地会话，并按配置跳转 IdP 登出；Accept: application/json 时返回 JSON
- GET  /api/auth/me/                当前用户；同时下发 csrftoken cookie，供前端提交 POST 请求
"""

import logging

import requests
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_safe
from joserfc.errors import JoseError

from apps.accounts import sso
from apps.core.audit import audit_log, build_operator

logger = logging.getLogger("accounts.sso")

LOGIN_URL = "/api/auth/login/"

# 访问 IdP 时的网络或响应格式错误
_IDP_UNAVAILABLE = (requests.RequestException, ValueError)


def _error_page(request, *, status, message, reason=None):
    """浏览器跳转场景下的错误页。reason 不为空时由 SecurityEventMiddleware 记录 SECURITY 日志（需 401/403）。"""
    response = render(
        request,
        "accounts/sso_error.html",
        {"message": message, "login_url": LOGIN_URL},
        status=status,
    )
    if reason:
        response.security_reason = f"sso:{reason}"
    return response


def _not_configured():
    return JsonResponse({"detail": "SSO is not configured"}, status=503)


def _idp_unavailable(request, exc):
    logger.error("sso: identity provider unavailable", exc_info=exc)
    return _error_page(
        request, status=502, message="暂时无法连接身份提供方，请稍后重试。"
    )


@require_safe
def login(request):
    if not sso.sso_enabled():
        return _not_configured()
    request.session[sso.SESSION_NEXT_KEY] = sso.safe_next(
        request, request.GET.get("next")
    )
    client = sso.get_client()
    try:
        sso.check_issuer(client)
        return client.authorize_redirect(request, settings.OIDC_REDIRECT_URI)
    except sso.SsoConfigError as exc:
        logger.error(f"sso: configuration error: {exc}")
        return _error_page(
            request, status=500, message="SSO 配置错误，请联系系统管理员。"
        )
    except _IDP_UNAVAILABLE as exc:
        return _idp_unavailable(request, exc)


@require_safe
def callback(request):
    if not sso.sso_enabled():
        return _not_configured()

    # IdP 直接返回错误，最常见的是用户未在 Okta 中分配到本应用（access_denied）
    idp_error = request.GET.get("error")
    if idp_error:
        if idp_error == "access_denied":
            message = "您没有本应用的访问权限，请通过 Okta 申请访问。"
        else:
            message = "身份提供方拒绝了登录请求，请重新登录或联系系统管理员。"
        return _error_page(
            request, status=403, message=message, reason=f"idp_error:{idp_error[:64]}"
        )

    client = sso.get_client()
    try:
        token = client.authorize_access_token(request)
        id_token_claims = token.get("userinfo")
        # Authlib 只在 state 中存有 nonce 时才校验 id_token；未经校验的身份一律不接受
        if not token.get("id_token") or not id_token_claims:
            raise sso.SsoDenied(
                "id_token_not_validated", "身份信息校验失败，请重新登录。"
            )
        userinfo = client.userinfo(token=token)
        claims = sso.merge_claims(id_token_claims, userinfo)
        result = sso.resolve_user(claims)
    except MismatchingStateError:
        # session 丢失（cookie 被拦截、换了浏览器、回调地址与登录地址不同域）或重复使用回调链接
        return _error_page(
            request,
            status=403,
            message="登录状态已失效，请重新登录。",
            reason="state_mismatch",
        )
    except sso.SsoDenied as exc:
        return _error_page(request, status=403, message=exc.message, reason=exc.reason)
    except OAuthError as exc:
        # token 端点返回错误，例如 invalid_grant（授权码过期或已使用）、invalid_client（Client Secret 错误）
        return _error_page(
            request,
            status=403,
            message="登录失败，请重新登录。",
            reason=f"oauth_error:{(exc.error or 'unknown')[:64]}",
        )
    except (AuthlibBaseError, JoseError) as exc:
        # id_token 签名、iss、aud、exp、nonce 校验失败
        return _error_page(
            request,
            status=403,
            message="身份信息校验失败，请重新登录。",
            reason=f"invalid_id_token:{type(exc).__name__}",
        )
    except _IDP_UNAVAILABLE as exc:
        return _idp_unavailable(request, exc)

    # 先取出 next：login() 在切换用户时会清空 session
    next_url = request.session.pop(sso.SESSION_NEXT_KEY, "/")
    auth_login(
        request, result.user, backend="django.contrib.auth.backends.ModelBackend"
    )
    # 登出 IdP 时需要 id_token_hint；session 存在服务端数据库，不下发给浏览器
    request.session[sso.SESSION_ID_TOKEN_KEY] = token["id_token"]

    if result.created or result.changes:
        audit_log(
            request,
            action="CREATE" if result.created else "UPDATE",
            resource_type="user",
            resource_id=result.user.pk,
            changes=sso.audit_changes(result),
        )
    logger.info(
        "sso: login succeeded",
        extra={"event": "login", "operator": build_operator(request)},
    )
    return HttpResponseRedirect(next_url)


@require_POST
def logout(request):
    """POST + CSRF，防止第三方页面诱导用户登出。"""
    operator = build_operator(request)
    id_token = request.session.get(sso.SESSION_ID_TOKEN_KEY)
    auth_logout(request)

    redirect_url = settings.OIDC_POST_LOGOUT_REDIRECT_URI or "/"
    if sso.sso_enabled() and settings.OIDC_LOGOUT_FROM_IDP:
        try:
            redirect_url = sso.logout_url(sso.get_client(), id_token) or redirect_url
        except _IDP_UNAVAILABLE as exc:
            # 本地会话已结束；IdP 会话仍在，记录后回到本地页面
            logger.warning("sso: idp logout unavailable", exc_info=exc)

    logger.info("sso: logout", extra={"event": "logout", "operator": operator})
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"redirect_url": redirect_url})
    return HttpResponseRedirect(redirect_url)


@require_safe
@ensure_csrf_cookie
def me(request):
    """匿名时返回 200 而不是 401：前端每次打开页面都会调用，401 会产生大量无意义的 SECURITY 日志。"""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(
            {
                "authenticated": False,
                "sso_enabled": sso.sso_enabled(),
                "login_url": LOGIN_URL,
            }
        )
    return JsonResponse(
        {
            "authenticated": True,
            "user": {
                "id": user.pk,
                "username": user.get_username(),
                "employee_number": user.employee_number,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
            },
        }
    )
