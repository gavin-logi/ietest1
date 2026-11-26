# 变更记录: 20261126-0841 新增：健康检查与 SPA 兜底页测试
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


class HealthTests(TestCase):
    def test_health(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_rejects_post(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)


class SpaIndexTests(TestCase):
    def test_missing_build_returns_404(self):
        with override_settings(FRONTEND_DIST_DIR=Path("/nonexistent")):
            self.assertEqual(self.client.get("/orders/42").status_code, 404)

    def test_serves_index_for_frontend_routes(self):
        with tempfile.TemporaryDirectory() as dist:
            (Path(dist) / "index.html").write_text(
                "<div id=app></div>", encoding="utf-8"
            )
            with override_settings(FRONTEND_DIST_DIR=Path(dist)):
                for path in ("/", "/orders/42"):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200, path)
                    self.assertIn(b"id=app", response.content)
                    self.assertEqual(response["Cache-Control"], "no-cache")

    def test_api_paths_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as dist:
            (Path(dist) / "index.html").write_text("spa", encoding="utf-8")
            with override_settings(FRONTEND_DIST_DIR=Path(dist)):
                self.assertEqual(self.client.get("/api/unknown/").status_code, 404)
