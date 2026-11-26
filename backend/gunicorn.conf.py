# 变更记录: 20261124-1607 新增：gunicorn 日志全部输出到 stdout 的单行 JSON 格式，替代入口脚本里的 --access-logfile/--error-logfile
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
loglevel = "info"

# "-" 在此处只表示“启用日志”，实际输出目标由下面的 logconfig_dict 统一指定为 stdout
accesslog = "-"
errorlog = "-"

LOG_HANDLER = "stdout"

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "logging_json.JsonFormatter"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        },
    },
    "root": {"handlers": [LOG_HANDLER], "level": "INFO"},
    "loggers": {
        "gunicorn.error": {
            "handlers": [LOG_HANDLER],
            "level": "INFO",
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": [LOG_HANDLER],
            "level": "INFO",
            "propagate": False,
        },
    },
}
