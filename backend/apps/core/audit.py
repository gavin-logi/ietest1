# 变更记录: 20261126-0841 新增：审计日志（AUDIT）与安全事件日志（SECURITY）工具，含敏感字段脱敏与大字段摘要
"""审计与安全事件日志，字段与规则见 AGENTS.md。

用法：
    # 写操作成功：默认在事务提交后输出；不在事务中时立即输出
    audit_log(request, action="UPDATE", resource_type="order", resource_id=order.pk,
              changes={"amount": {"before": 100, "after": 200}})

    # 写操作失败：在 except 中调用，自动附带 stack_trace
    except Exception:
        audit_log(request, action="UPDATE", resource_type="order", resource_id=pk,
                  status=FAILURE, exc_info=True)
        raise

    # 认证或授权被拒绝：一般由 SecurityEventMiddleware 自动记录，视图只需设置原因
    response = JsonResponse({...}, status=403)
    response.security_reason = "not_project_member"

任何情况下都不会抛出异常影响业务；构造失败时输出一条降级日志。
"""

import hashlib
import json
import logging
import re

from django.db import transaction

from apps.core.request_context import client_ip_var, get_client_ip, trace_id_var

audit_logger = logging.getLogger("audit")
security_logger = logging.getLogger("security")

SUCCESS = "SUCCESS"
FAILURE = "FAILURE"
DENIED = "DENIED"
REDACTED = "***REDACTED***"

# 键名命中即整体脱敏：密码、密钥、令牌、证件号、手机号、银行卡等
_SENSITIVE_KEY = re.compile(
    r"pass(word|wd)?|secret|token|api[_-]?key|credential|private[_-]?key"
    r"|national[_-]?id|id[_-]?(card|number|no)|ssn|passport"
    r"|phone|mobile|tel(ephone)?$|bank|card[_-]?(no|number)|iban|cvv",
    re.IGNORECASE,
)

# 单个字符串值超过该长度时只记录长度与摘要（富文本、Base64、大 JSON 等）
MAX_VALUE_CHARS = 512
# 整个 changes 序列化后超过该长度时整体替换为摘要，避免单行日志超过 Docker 16KB 限制
MAX_CHANGES_CHARS = 8000
_MAX_DEPTH = 5
_MAX_ITEMS = 50


def _digest(text):
    return {
        "length": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
    }


def _sanitize(value, depth=0):
    if depth > _MAX_DEPTH:
        return "***TRUNCATED***"
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            key = str(key)
            result[key] = (
                REDACTED if _SENSITIVE_KEY.search(key) else _sanitize(item, depth + 1)
            )
        return result
    if isinstance(value, list | tuple | set):
        return [_sanitize(item, depth + 1) for item in list(value)[:_MAX_ITEMS]]
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value)
    return _digest(text) if len(text) > MAX_VALUE_CHARS else text


def sanitize_changes(changes):
    """脱敏并控制体积。传入 None 时返回空字典。"""
    if not changes:
        return {}
    cleaned = _sanitize(changes)
    serialized = json.dumps(cleaned, default=str, ensure_ascii=False)
    if len(serialized) > MAX_CHANGES_CHARS:
        return {"_truncated": True, **_digest(serialized)}
    return cleaned


def build_operator(request):
    """操作者信息。匿名用户按 AGENTS.md：user_id 为空、username 为 GUEST；无请求（系统任务）时为 SYSTEM。"""
    if request is None:
        return {"user_id": "", "username": "SYSTEM", "client_ip": ""}
    client_ip = client_ip_var.get() or get_client_ip(request)
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return {
            "user_id": str(user.pk),
            "username": user.get_username(),
            "client_ip": client_ip,
        }
    return {"user_id": "", "username": "GUEST", "client_ip": client_ip}


def _fallback(logger, message):
    try:
        logger.error(message, extra={"log_type": "APP"})
    except Exception:  # noqa: BLE001 - 日志不能影响业务
        pass


def audit_log(
    request,
    *,
    action,
    resource_type,
    resource_id,
    changes=None,
    status=SUCCESS,
    exc_info=None,
    on_commit=True,
):
    """输出一条 AUDIT 日志。

    成功的写操作默认通过 transaction.on_commit 在事务提交后输出（事务回滚则不输出）；
    失败时立即以 ERROR 级别输出，exc_info=True 会附带 stack_trace。
    """
    try:
        fields = {
            "log_type": "AUDIT",
            "trace_id": trace_id_var.get(),
            "operator": build_operator(request),
            "action": str(action),
            "resource": {
                "type": str(resource_type),
                "id": "" if resource_id is None else str(resource_id),
            },
            "changes": sanitize_changes(changes),
            "status": status,
        }
        message = f"{fields['action']} {fields['resource']['type']}"
    except Exception:  # noqa: BLE001
        _fallback(audit_logger, "audit log construction failed")
        return

    def emit():
        try:
            if status == SUCCESS:
                audit_logger.info(message, extra=fields)
            else:
                audit_logger.error(message, extra=fields, exc_info=exc_info)
        except Exception:  # noqa: BLE001
            _fallback(audit_logger, "audit log emit failed")

    if status == SUCCESS and on_commit:
        transaction.on_commit(emit)
    else:
        emit()


def security_log(request, *, reason, http_status=None):
    """输出一条 SECURITY 日志（401 / 403 等拒绝事件），级别 WARN，status 固定为 DENIED。

    path 只记录路径，不含查询串：查询串中可能带有授权码、令牌等敏感信息。
    """
    try:
        operator = build_operator(request)
        fields = {
            "log_type": "SECURITY",
            "trace_id": trace_id_var.get(),
            "operator": operator,
            "client_ip": operator["client_ip"],
            "method": request.method,
            "path": request.path,
            "reason": str(reason),
            "status": DENIED,
        }
        if http_status is not None:
            fields["http_status"] = int(http_status)
        security_logger.warning(f"access denied: {fields['reason']}", extra=fields)
    except Exception:  # noqa: BLE001
        _fallback(security_logger, "security log failed")
