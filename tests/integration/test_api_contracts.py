"""既有只读 Checker/Profile HTTP API 的响应合同回归测试。"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import studio.server as studio_server
from engine.core.paths import PlatformPaths


class TestReadApiContracts(unittest.TestCase):
    def setUp(self):
        self.token = patch.object(studio_server, "STUDIO_TOKEN", "")
        self.token.start()
        self.client = studio_server.app.test_client()

    def tearDown(self):
        self.token.stop()

    def test_checker_response_keeps_existing_fields_and_adds_status_summary(self):
        response = self.client.post("/api/checker/security", json={"dir": str(PlatformPaths.ENGINE_DIR), "run_id": "api-fixture-1"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue({"ok", "name", "pass", "total", "checks", "status_summary"}.issubset(payload))
        self.assertEqual(payload["name"], "security")

    def test_profile_read_api_exposes_versioned_profile(self):
        response = self.client.get("/api/profiles/fixture-local")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["ref"], "fixture-local@1")
        self.assertEqual(payload["profile"]["delivery"], "local_artifact")

    def test_plan_review_preview_is_read_only_and_returns_frozen_components(self):
        task = {
            "id": "draft-plan-review", "title": "Plan review fixture",
            "source": "studio_text", "priority": 2, "spec_text": "离线需求",
        }
        response = self.client.post("/api/run-plans/preview", json={
            "profile_id": "fixture-local", "task": task,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        plan = payload["plan"]
        self.assertEqual(plan["profile"]["ref"], "fixture-local@1")
        self.assertEqual(plan["components"], {
            "source": "local_queue", "compiler": "simple", "maker": "sample",
            "checkers": ["security"], "delivery": "local_artifact",
        })
        self.assertEqual(plan["task"]["id"], "draft-plan-review")


if __name__ == "__main__":
    unittest.main()
