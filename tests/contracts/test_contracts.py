"""Phase 2 数据合同的离线回归测试。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.contracts import (ArtifactBundle, CheckReport, DeliveryResult,
                                  RunEvent, SpecBundle)


class TestContracts(unittest.TestCase):
    def test_bundles_are_json_serializable(self):
        values = [
            ArtifactBundle("output/run", ["app.py"], "digest"),
            CheckReport(status="passed", checks=[{"name": "security", "status": "passed"}]),
            DeliveryResult(status="plan_only", plan={"dry_run": True}),
            RunEvent("run-1", "fixture-local@1", "task-1", status="skipped"),
        ]
        encoded = json.dumps([value.to_dict() for value in values])
        self.assertIn('"run-1"', encoded)

    def test_spec_bundle_requires_all_three_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [os.path.join(directory, name) for name in ("spec.md", "manifest.json", "acceptance.json")]
            for path in paths:
                open(path, "w").close()
            bundle = SpecBundle(*paths)
            self.assertTrue(bundle.validate())
            os.unlink(paths[-1])
            self.assertFalse(bundle.validate())

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            CheckReport(status="green")
        with self.assertRaises(ValueError):
            DeliveryResult(status="deploying")
        with self.assertRaises(ValueError):
            RunEvent("run-1", "profile", "task", status="unknown")


if __name__ == "__main__":
    unittest.main()
