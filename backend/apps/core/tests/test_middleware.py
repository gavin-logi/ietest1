# 变更记录: 20261126-0841 新增：trace_id、客户端 IP、401/403 安全日志、CSRF 失败的测试
import io
import json
import logging

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.core.log_filters import RequestContextFilter
from apps.core.request_context import trace_id_var
from logging_json import JsonFormatter


@override_settings(ROOT_URLCONF="apps.core.tests.urls")
class TraceIdTests(TestCase):
    def test_generates_trace_id_header(self):
        response = self.client.get("/writes-log/")
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_reuses_valid_incoming_trace_id(self):
        response = self.client.get(
            "/writes-log/", headers={"X-Request-ID": "req-98a7b6c5"}
        )
        self.assertEqual(response["X-Request-ID"], "req-98a7b6c5")

    def test_replaces_invalid_incoming_trace_id(self):
        response = self.client.get(
            "/writes-log/", headers={"X-Request-ID": "bad id\nwith newline"}
        )
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_logs_inside_request_carry_trace_id(self):
        with self.assertLogs("apps.test", level="INFO") as captured:
            response = self.client.get(
                "/writes-log/", headers={"X-Request-ID": "req-1"}
            )
        # assertLogs 的处理器不经过 settings 中的过滤器，这里手动套用一次，验证过滤器读取的上下文正确
        record = captured.records[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(getattr(record, "trace_id", None), None)
        token = trace_id_var.set("req-1")
        try:
            RequestContextFilter().filter(record)
        finally:
            trace_id_var.reset(token)
        self.assertEqual(record.trace_id, "req-1")

    def test_context_is_reset_after_request(self):
        self.client.get("/writes-log/")
        self.assertEqual(trace_id_var.get(), "")


class JsonOutputTests(TestCase):
    def test_single_line_json_with_trace_id_and_stack_trace(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RequestContextFilter())
        logger = logging.getLogger("apps.test.json")
        logger.addHandler(handler)
        logger.propagate = False
        token = trace_id_var.set("req-abc")
        try:
            try:
                raise ValueError("boom")
            except ValueError:
                logger.exception("failed")
        finally:
            trace_id_var.reset(token)
            logger.removeHandler(handler)
        output = stream.getvalue().strip()
        self.assertEqual(len(output.splitlines()), 1)
        payload = json.loads(output)
        self.assertEqual(payload["level"], "ERROR")
        self.assertEqual(payload["trace_id"], "req-abc")
        self.assertIn("ValueError: boom", payload["stack_trace"])
        self.assertTrue(payload["timestamp"].endswith("Z"))


@override_settings(ROOT_URLCONF="apps.core.tests.urls")
class SecurityEventTests(TestCase):
    def _security_record(self, method, path, **kwargs):
        with self.assertLogs("security", level="WARNING") as captured:
            getattr(self.client, method)(path, **kwargs)
        self.assertEqual(len(captured.records), 1)
        return captured.records[0]

    def test_403_anonymous(self):
        record = self._security_record(
            "get", "/denied/?code=secret-value", REMOTE_ADDR="10.0.0.5"
        )
        self.assertEqual(record.levelname, "WARNING")
        self.assertEqual(record.log_type, "SECURITY")
        self.assertEqual(record.status, "DENIED")
        self.assertEqual(record.reason, "forbidden")
        self.assertEqual(record.method, "GET")
        self.assertEqual(record.path, "/denied/")  # 不含查询串
        self.assertEqual(record.client_ip, "10.0.0.5")
        self.assertEqual(
            record.operator,
            {"user_id": "", "username": "GUEST", "client_ip": "10.0.0.5"},
        )
        self.assertRegex(record.trace_id, r"^[0-9a-f]{32}$")
        self.assertEqual(record.http_status, 403)

    def test_401(self):
        record = self._security_record("get", "/unauthenticated/")
        self.assertEqual(record.reason, "unauthenticated")
        self.assertEqual(record.http_status, 401)

    def test_view_supplied_reason_and_authenticated_operator(self):
        user = get_user_model().objects.create_user(
            username="zhangsan", employee_number="10086"
        )
        self.client.force_login(user)
        record = self._security_record("get", "/denied-reason/")
        self.assertEqual(record.reason, "not_project_member")
        self.assertEqual(record.operator["user_id"], str(user.pk))
        self.assertEqual(record.operator["username"], "zhangsan")

    def test_no_security_log_for_success(self):
        with self.assertNoLogs("security", level="WARNING"):
            self.client.get("/writes-log/")

    def test_csrf_failure_returns_json_and_logs(self):
        client = Client(enforce_csrf_checks=True)
        with self.assertLogs("security", level="WARNING") as captured:
            response = client.post("/post/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF verification failed"})
        self.assertTrue(captured.records[0].reason.startswith("csrf_failed"))


@override_settings(ROOT_URLCONF="apps.core.tests.urls")
class ClientIpTests(TestCase):
    def _ip(self, **meta):
        with self.assertLogs("security", level="WARNING") as captured:
            self.client.get("/denied/", **meta)
        return captured.records[0].client_ip

    def test_ignores_forwarded_for_without_trusted_proxy(self):
        self.assertEqual(
            self._ip(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4"), "10.0.0.1"
        )

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_takes_rightmost_hop_behind_one_proxy(self):
        # 客户端伪造的 6.6.6.6 在左侧，ALB 追加的真实地址在最右侧
        ip = self._ip(
            REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9"
        )
        self.assertEqual(ip, "203.0.113.9")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_falls_back_to_remote_addr_without_header(self):
        self.assertEqual(self._ip(REMOTE_ADDR="10.0.0.1"), "10.0.0.1")
