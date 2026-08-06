"""Compiler 与本地 Delivery Port 的离线合同回归测试。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.compilers import load_compiler
from engine.core.contracts import ArtifactBundle, RunContext
from engine.core.paths import PlatformPaths
from pipeline.delivery import load_delivery


class TestCompilerAndDeliveryPorts(unittest.TestCase):
    def setUp(self):
        self.context = RunContext("run-port-001", "fixture-local@1", str(PlatformPaths.ROOT), "pomodoro")

    def test_simple_compiler_reuses_existing_spec_bundle_without_subprocess(self):
        compiler = load_compiler("simple")
        with patch("engine.compilers.simple.subprocess.run") as run:
            bundle = compiler.compile(self.context, "离线测试不应重新编译已有 case")

        run.assert_not_called()
        self.assertTrue(bundle.validate())
        self.assertEqual(bundle.provenance, "simple")
        self.assertEqual(bundle.meta, {"source": "existing"})

    def test_local_artifact_plan_is_plan_only_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = str(Path(directory) / "artifact")
            artifacts = ArtifactBundle(output_dir, ["index.html"], "artifact-digest")
            result = load_delivery("local_artifact").plan(self.context, artifacts)

            self.assertEqual(result.status, "plan_only")
            self.assertEqual(result.meta, {"adapter": "local_artifact", "dry_run": True})
            self.assertEqual(result.plan["digest"], "artifact-digest")
            self.assertFalse(Path(result.location).exists())

    def test_local_artifact_delivery_writes_only_its_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = str(Path(directory) / "artifact")
            artifacts = ArtifactBundle(output_dir, ["index.html"], "artifact-digest")
            result = load_delivery("local_artifact").deliver(self.context, artifacts)

            self.assertEqual(result.status, "passed")
            self.assertTrue(Path(result.location).is_file())
            with open(result.location, encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(persisted, result.plan)
            self.assertEqual(persisted["run_id"], self.context.run_id)
            self.assertEqual(persisted["files"], ["index.html"])


if __name__ == "__main__":
    unittest.main()
