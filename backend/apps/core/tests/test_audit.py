# 变更记录: 20261126-0841 新增：审计日志的字段、事务提交后输出、脱敏与大字段摘要测试
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.audit import (
    FAILURE,
    MAX_VALUE_CHARS,
    REDACTED,
    audit_log,
    build_operator,
    sanitize_changes,
)
from apps.core.request_context import trace_id_var


class SanitizeTests(TestCase):
    def test_redacts_sensitive_keys(self):
        cleaned = sanitize_changes(
            {
                "password": {"before": "a", "after": "b"},
                "api_secret": "x",
                "phone": "13800000000",
                "id_number": "110101",
                "bank_card_no": "6222",
                "budget": {"before": 50000, "after": 80000},
                "employee_number": "10086",
            }
        )
        for key in ("password", "api_secret", "phone", "id_number", "bank_card_no"):
            self.assertEqual(cleaned[key], REDACTED, key)
        self.assertEqual(cleaned["budget"], {"before": 50000, "after": 80000})
        self.assertEqual(cleaned["employee_number"], "10086")

    def test_redacts_nested_keys(self):
        cleaned = sanitize_changes(
            {"profile": {"after": {"mobile": "1", "city": "SZ"}}}
        )
        self.assertEqual(
            cleaned["profile"]["after"], {"mobile": REDACTED, "city": "SZ"}
        )

    def test_large_value_becomes_digest(self):
        cleaned = sanitize_changes({"content": "x" * (MAX_VALUE_CHARS + 1)})
        self.assertEqual(cleaned["content"]["length"], MAX_VALUE_CHARS + 1)
        self.assertEqual(len(cleaned["content"]["sha256"]), 64)

    def test_oversized_changes_are_summarised(self):
        cleaned = sanitize_changes({f"field_{i}": "y" * 400 for i in range(40)})
        self.assertTrue(cleaned["_truncated"])

    def test_none_and_unserialisable_values_are_safe(self):
        self.assertEqual(sanitize_changes(None), {})
        cleaned = sanitize_changes({"blob": b"\x00\x01", "obj": object(), "n": None})
        self.assertEqual(cleaned["blob"], {"bytes": 2})
        self.assertIsInstance(cleaned["obj"], str)
        self.assertIsNone(cleaned["n"])


class OperatorTests(TestCase):
    def test_anonymous_is_guest(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.20.1.55")
        request.user = AnonymousUser()
        self.assertEqual(
            build_operator(request),
            {"user_id": "", "username": "GUEST", "client_ip": "10.20.1.55"},
        )

    def test_no_request_is_system(self):
        self.assertEqual(build_operator(None)["username"], "SYSTEM")


class AuditLogTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().post("/", REMOTE_ADDR="10.20.1.55")
        self.request.user = AnonymousUser()

    def test_success_waits_for_commit(self):
        token = trace_id_var.set("req-98a7b6c5")
        try:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                with self.assertNoLogs("audit"):
                    audit_log(
                        self.request,
                        action="UPDATE",
                        resource_type="project_config",
                        resource_id="proj_42",
                        changes={
                            "budget": {"before": 50000, "after": 80000},
                            "api_secret": "s",
                        },
                    )
            self.assertEqual(len(callbacks), 1)
            with self.assertLogs("audit", level="INFO") as captured:
                callbacks[0]()
        finally:
            trace_id_var.reset(token)
        record = captured.records[0]
        self.assertEqual(record.levelname, "INFO")
        self.assertEqual(record.log_type, "AUDIT")
        self.assertEqual(record.trace_id, "req-98a7b6c5")
        self.assertEqual(record.action, "UPDATE")
        self.assertEqual(record.resource, {"type": "project_config", "id": "proj_42"})
        self.assertEqual(record.changes["api_secret"], REDACTED)
        self.assertEqual(record.status, "SUCCESS")
        self.assertEqual(record.operator["username"], "GUEST")

    def test_failure_is_immediate_with_stack_trace(self):
        with self.assertLogs("audit", level="ERROR") as captured:
            try:
                raise RuntimeError("db down")
            except RuntimeError:
                audit_log(
                    self.request,
                    action="DELETE",
                    resource_type="order",
                    resource_id=7,
                    status=FAILURE,
                    exc_info=True,
                )
        record = captured.records[0]
        self.assertEqual(record.levelname, "ERROR")
        self.assertEqual(record.status, "FAILURE")
        self.assertEqual(record.resource["id"], "7")
        self.assertIsNotNone(record.exc_info)

    def test_never_raises_on_bad_input(self):
        class Broken:
            def __str__(self):
                raise RuntimeError("cannot stringify")

        # 构造失败时只输出降级日志，不向业务抛异常
        with self.assertLogs("audit", level="ERROR"):
            audit_log(
                self.request,
                action=Broken(),
                resource_type="x",
                resource_id=1,
                on_commit=False,
            )
