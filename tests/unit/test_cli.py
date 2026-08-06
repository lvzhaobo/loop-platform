"""无副作用 Profile CLI 测试。"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine import cli


class TestProfileCli(unittest.TestCase):
    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(list(args))
        return code, json.loads(output.getvalue())

    def test_list_and_validate_are_read_only(self):
        code, payload = self.invoke("profile", "list")
        self.assertEqual(code, 0)
        profile_ids = [item["id"] for item in payload["profiles"]]
        self.assertTrue({"fixture-local", "api-batch", "mumuspec-local"}.issubset(profile_ids))

        for profile_id, expected_ref in {
            "fixture-local": "fixture-local@1",
            "api-batch": "api-batch@1",
            "mumuspec-local": "mumuspec-local@1",
        }.items():
            code, payload = self.invoke("profile", "validate", profile_id)
            self.assertEqual(code, 0)
            self.assertEqual(payload["ref"], expected_ref)

    def test_plan_dry_run_does_not_persist(self):
        expectations = {
            "fixture-local": {"compiler": "simple", "maker": "sample"},
            "api-batch": {"compiler": "simple", "maker": "deepseek"},
            "mumuspec-local": {"compiler": "mumuspec", "maker": "sample"},
        }
        for profile_id, components in expectations.items():
            code, payload = self.invoke("plan", "--profile", profile_id, "--dry-run")
            self.assertEqual(code, 0)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["plan"]["status"], "planned")
            self.assertEqual(payload["plan"]["task"]["id"], "fixture-pomodoro")
            self.assertEqual(payload["plan"]["components"], {
                "source": "local_queue", "checkers": ["security"],
                "delivery": "local_artifact", **components,
            })


if __name__ == "__main__":
    unittest.main()
