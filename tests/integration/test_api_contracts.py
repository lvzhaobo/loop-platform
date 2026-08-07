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
    def test_requirement_and_backlog_reads_hide_stored_body_and_tokens(self):
        import json
        import tempfile
        from pathlib import Path

        hidden = "api_key=example-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            (data_dir / "backlog.json").write_text(json.dumps({"docs": [{
                "id": "FS-900", "title": hidden, "priority": 1, "profile_id": "deepseek-local",
                "spec_text": f"Private requirement: {hidden}", "wiki_token": "private-token",
            }]}), encoding="utf-8")
            (data_dir / "state.json").write_text("{}", encoding="utf-8")
            with patch.object(PlatformPaths, "DATA_DIR", data_dir):
                requirements = self.client.get("/api/requirements")
                backlog = self.client.get("/api/backlog")

        self.assertEqual(requirements.status_code, 200)
        self.assertEqual(backlog.status_code, 200)
        requirement = requirements.get_json()["requirements"][0]
        backlog_item = backlog.get_json()["docs"][0]
        self.assertEqual(requirement["title"], "需求 FS-900")
        self.assertIn("不展示原文", requirement["description"])
        self.assertNotIn(hidden, json.dumps({"requirements": requirement, "backlog": backlog_item}))
        self.assertNotIn("spec_text", backlog_item)
        self.assertNotIn("token", backlog_item)

    def test_frozen_plan_must_match_confirmation_before_executor_is_called(self):
        import tempfile
        from pathlib import Path
        from adapters.base import Task
        from engine.core.profiles import get_run_plan, load_profile

        profile = load_profile("fixture-local")
        task = Task(id="frozen-api-task", title="Frozen API task", source="local", case="pomodoro",
                    spec_text="离线需求", priority=2, profile_id="fixture-local")
        with tempfile.TemporaryDirectory() as directory:
            with (patch.object(PlatformPaths, "RUN_PLANS_DIR", Path(directory) / "plans"),
                  patch.object(studio_server, "_pending_profile_task", return_value=(profile, task))):
                frozen = self.client.post("/api/run-plans/freeze", json={
                    "profile_id": profile.id, "task_id": task.id,
                })
                self.assertEqual(frozen.status_code, 200)
                plan = frozen.get_json()["plan"]
                self.assertEqual(get_run_plan(plan["id"])["digest"], plan["digest"])
                with patch("engine.core.run_executor.ProfileRunExecutor.execute_plan") as execute_plan:
                    rejected = self.client.post("/api/profile-runs/confirm", json={
                        "confirmed": True, "profile_id": profile.id, "task_id": task.id,
                        "plan_id": plan["id"], "plan_digest": "not-the-reviewed-digest",
                    })

        self.assertEqual(rejected.status_code, 400)
        self.assertIn("digest", rejected.get_json()["error"])
        execute_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
