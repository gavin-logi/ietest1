# 变更记录: 20261126-0841 新增：用 contextvars 保存当前请求的 trace_id 与客户端 IP，供日志与审计读取
"""当前请求的上下文。

contextvars 在线程与协程之间相互隔离，gunicorn 多线程或将来改用 ASGI 都不会串号。
请求结束时由 RequestContextMiddleware 负责还原，避免线程复用时泄漏到下一个请求。
"""

import re
import uuid
from contextvars import ContextVar

from django.conf import settings

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
client_ip_var: ContextVar[str] = ContextVar("client_ip", default="")

# 上游传入的请求 ID 只接受安全字符，防止日志注入或超长值
_VALID_TRACE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

TRACE_ID_HEADER = "X-Request-ID"


def new_trace_id():
    return uuid.uuid4().hex


def resolve_trace_id(request):
    """优先沿用上游（网关、前端）传入的 X-Request-ID，格式不合法时重新生成。"""
    incoming = request.headers.get(TRACE_ID_HEADER, "")
    if incoming and _VALID_TRACE_ID.match(incoming):
        return incoming
    return new_trace_id()


def get_client_ip(request):
    """取真实客户端 IP。

    只有配置了 TRUSTED_PROXY_COUNT 时才读取 X-Forwarded-For，并从右往左取第 N 个：
    每一层可信代理都会把它看到的对端地址追加到末尾，左侧的值可能是客户端伪造的。
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxy_count <= 0:
        return remote_addr
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if len(hops) >= proxy_count:
        return hops[-proxy_count]
    return remote_addr
