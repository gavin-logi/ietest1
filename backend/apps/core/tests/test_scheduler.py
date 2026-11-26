# 变更记录: 20261126-1058 新增：定时任务骨架测试（启动日志、心跳、SIGTERM 优雅退出）
import os
import signal
import threading
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase


class RunSchedulerTests(SimpleTestCase):
    def setUp(self):
        previous = {
            sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        self.addCleanup(lambda: [signal.signal(s, h) for s, h in previous.items()])

    def test_starts_heartbeats_and_stops_on_sigterm(self):
        # 0.3 秒后发送 SIGTERM，命令应在约 0.3 秒内返回，而不是等待心跳
        timer = threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertLogs("scheduler", level="INFO") as captured:
            call_command("run_scheduler", heartbeat=60, stdout=StringIO())
        messages = [record.getMessage() for record in captured.records]
        self.assertIn("scheduler: started", messages)
        self.assertIn("scheduler: stop requested", messages)
        self.assertIn("scheduler: stopped", messages)
        self.assertNotIn("scheduler: heartbeat", messages)

    def test_emits_heartbeat(self):
        timer = threading.Timer(1.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertLogs("scheduler", level="INFO") as captured:
            call_command("run_scheduler", heartbeat=1, stdout=StringIO())
        self.assertIn(
            "scheduler: heartbeat", [record.getMessage() for record in captured.records]
        )
