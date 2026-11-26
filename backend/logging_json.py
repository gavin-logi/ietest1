# 变更记录: 20261125-1035 修复：保留 extra= 传入的扩展字段（log_type、operator、status 等）；WARNING 映射为 WARN；改用 datetime.UTC
import json
import logging
import traceback
from datetime import UTC, datetime

# 日志级别名称映射：规范使用 WARN
_LEVEL_NAMES = {"WARNING": "WARN"}

# LogRecord 自带的属性，不属于扩展字段
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
}

# 核心字段由格式化器统一生成，extra= 不允许覆盖
_PROTECTED_KEYS = {"timestamp", "level", "logger", "message", "stack_trace"}


class JsonFormatter(logging.Formatter):
    """每条日志输出为一行 JSON；格式化失败时降级输出，绝不抛异常阻塞业务。

    通过 logger.xxx(msg, extra={...}) 传入的字段会原样保留在 JSON 中，
    例如 log_type、operator、status、trace_id。核心字段（timestamp、level、logger、message、stack_trace）不会被覆盖。
    """

    def format(self, record):
        try:
            payload = {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": _LEVEL_NAMES.get(record.levelname, record.levelname),
                "log_type": "APP",
                "logger": record.name,
                "message": record.getMessage(),
            }
            for key, value in vars(record).items():
                if key in _STANDARD_ATTRS or key in _PROTECTED_KEYS:
                    continue
                payload[key] = value
            if record.exc_info:
                payload["stack_trace"] = "".join(
                    traceback.format_exception(*record.exc_info)
                ).rstrip()
            return json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001 - 日志本身不能让业务崩溃
            return json.dumps(
                {
                    "level": "ERROR",
                    "log_type": "APP",
                    "message": "log formatting failed",
                    "logger": getattr(record, "name", "unknown"),
                }
            )
