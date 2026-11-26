# 变更记录: 20261126-1058 新增：定时任务进程骨架（不注册任何任务）。保持常驻、输出心跳到 stdout、收到 SIGTERM/SIGINT 后优雅退出
import logging
import signal
import threading

from django.core.management.base import BaseCommand

logger = logging.getLogger("scheduler")


class Command(BaseCommand):
    help = "定时任务进程（骨架）：当前没有任务，只保持进程运行并输出心跳日志。部署时副本数必须为 1。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--heartbeat",
            type=int,
            default=60,
            help="心跳日志间隔（秒）",
        )

    def handle(self, *args, **options):
        stop = threading.Event()

        def request_stop(signum, _frame):
            logger.info("scheduler: stop requested", extra={"signal": signum})
            stop.set()

        # 信号处理只能在主线程注册；manage.py 与 gunicorn 都满足该条件
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

        logger.info("scheduler: started", extra={"jobs": 0})
        while not stop.wait(options["heartbeat"]):
            logger.info("scheduler: heartbeat", extra={"jobs": 0})
        logger.info("scheduler: stopped")
