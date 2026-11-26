# 变更记录: 20261126-0841 新增：日志过滤器，为每条日志自动附加当前请求的 trace_id
import logging

from apps.core.request_context import trace_id_var


class RequestContextFilter(logging.Filter):
    """把 trace_id 写入 LogRecord，JsonFormatter 会将其作为扩展字段输出。

    调用方通过 extra= 显式传入的 trace_id 优先；请求之外（如定时任务）没有 trace_id 时不添加该字段。
    """

    def filter(self, record):
        if not getattr(record, "trace_id", None):
            trace_id = trace_id_var.get()
            if trace_id:
                record.trace_id = trace_id
        return True
