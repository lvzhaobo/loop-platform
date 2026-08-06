"""Production Studio entry keeps Delivery Runs bound to observability only."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import studio.server as studio_server
from engine.core.paths import PlatformPaths


class TestStudioDeliveryRunsShell(unittest.TestCase):
    def setUp(self):
        self.token = patch.object(studio_server, "STUDIO_TOKEN", "")
        self.token.start()
        self.client = studio_server.app.test_client()
        self.script = (PlatformPaths.STUDIO_DIR / "static" / "js" / "platform.js").read_text(encoding="utf-8")

    def tearDown(self):
        self.token.stop()

    def test_production_shell_loads_the_delivery_runs_view(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/js/platform.js', response.get_data(as_text=True))
        self.assertIn("function installDeliveryRunsView", self.script)
        self.assertIn("page-delivery-runs", self.script)
        self.assertIn("交付运行（只读）", self.script)

    def test_delivery_runs_uses_only_the_authoritative_read_api(self):
        view = self.script.split("/* ===== Phase 4：权威交付运行（只读） ===== */", 1)[1]
        self.assertIn("/api/observability/runs?limit=50", view)
        self.assertIn("/api/observability/runs/", view)
        self.assertIn("/api/observability/lifecycle?limit=100", view)
        self.assertIn("/api/observability/governance-coverage?limit=100", view)
        self.assertNotIn("/api/trace", view)
        self.assertNotIn("/api/output", view)
        self.assertNotIn("apiPost", view)
        for status in ("passed", "failed", "unavailable", "indeterminate", "skipped"):
            self.assertIn(status, view)


if __name__ == "__main__":
    unittest.main()
