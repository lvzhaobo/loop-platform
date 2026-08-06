"""Phase 2 Maker/Checker 兼容适配层的离线回归测试。"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.compat import check_with_context, make_with_context
from engine.core.contracts import RunContext, SpecBundle
from engine.core.paths import PlatformPaths


class TestCompatAdapters(unittest.TestCase):
    def test_sample_maker_and_security_checker_share_contract(self):
        context = RunContext("run-compat-001", "fixture-local@1", "workspace", "pomodoro")
        with tempfile.TemporaryDirectory() as directory:
            paths = [os.path.join(directory, name) for name in ("spec.md", "manifest.json", "acceptance.json")]
            for path in paths:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("{}")
            with patch.object(PlatformPaths, "OUTPUT_DIR", PlatformPaths.resolve(directory)):
                artifacts = make_with_context(context, SpecBundle(*paths), maker_name="sample")
                report = check_with_context(context, artifacts, checker_names=["security"])
        self.assertIn("index.html", artifacts.files)
        self.assertTrue(artifacts.digest)
        self.assertEqual(report.status, "passed")
        self.assertEqual(report.checks[0]["checker"], "security")

    def test_unknown_checker_becomes_unavailable_evidence(self):
        context = RunContext("run-compat-002", "fixture-local@1", "workspace", "pomodoro")
        with tempfile.TemporaryDirectory() as directory:
            report = check_with_context(context, type("Artifact", (), {"output_dir": directory})(), ["missing"])
        self.assertEqual(report.status, "indeterminate")
        self.assertEqual(report.checks[0]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
