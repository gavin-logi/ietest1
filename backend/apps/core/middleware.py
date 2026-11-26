# 变更记录: 20261126-0841 新增：RequestContextMiddleware（trace_id、客户端 IP）与 SecurityEventMiddleware（401/403 安全日志）
from apps.core.audit import security_log
from apps.core.request_context import (
    TRACE_ID_HEADER,
    client_ip_var,
    get_client_ip,
    resolve_trace_id,
    trace_id_var,
)

_DEFAULT_REASONS = {
    401: "unauthenticated",
    403: "forbidden",
}


class RequestContextMiddleware:
    """为每个请求确定 trace_id 与客户端 IP，写入上下文，并通过 X-Request-ID 响应头返回 trace_id。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = resolve_trace_id(request)
        client_ip = get_client_ip(request)
        request.trace_id = trace_id
        request.client_ip = client_ip
        trace_token = trace_id_var.set(trace_id)
        ip_token = client_ip_var.set(client_ip)
        try:
            response = self.get_response(request)
            response[TRACE_ID_HEADER] = trace_id
            return response
        finally:
            trace_id_var.reset(trace_token)
            client_ip_var.reset(ip_token)


class SecurityEventMiddleware:
    """响应码为 401 / 403 时记录 SECURITY 日志。

    视图可以通过 response.security_reason = "..." 提供具体原因；未提供时使用通用原因。
    若视图已自行调用 security_log，可设置 response.security_logged = True 避免重复记录。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code in _DEFAULT_REASONS and not getattr(
            response, "security_logged", False
        ):
            reason = (
                getattr(response, "security_reason", "")
                or _DEFAULT_REASONS[response.status_code]
            )
            security_log(request, reason=reason, http_status=response.status_code)
        return response
