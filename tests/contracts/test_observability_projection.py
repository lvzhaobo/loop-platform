"""RunEvent 到只读 observability 投影的五态回归。"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import RunEvent
from engine.core.observability_projection import ObservabilityProjection

DIGEST = "a" * 64
DIGESTS = {
    "source": {"input": DIGEST},
    "compiler": {"input": DIGEST, "spec": DIGEST, "acceptance": DIGEST},
}


class TestObservabilityProjection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        evidence = EvidenceStore(root / "evidence")
        self.events = EventStore(root / "events", evidence_store=evidence)
        self.projection = ObservabilityProjection(self.events)
        self.evidence = evidence

    def tearDown(self):
        self.temp.cleanup()

    def _append(self, run_id, stage, status, sequence, *, occurred_at=None):
        digests = DIGESTS[stage] if status == "passed" else {"input": DIGEST}
        evidence = (self.evidence.put_json({"stage": stage, "status": status}, source=stage,
                                            run_id=run_id, plan_digest=DIGEST,
                                            kind=f"{stage}-{sequence}"),)
        self.events.append(RunEvent(
            event_id=f"{run_id}-{sequence}", run_id=run_id, sequence=sequence,
            occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(), stage=stage, status=status,
            profile_ref="fixture-local@1", task_id="fixture-task", plan_digest=DIGEST,
            digests=digests, component_versions={"test": "1"}, evidence=evidence,
            details={"local_path": str(self.temp.name), "secret": "not-projectable"},
        ))

    def test_five_statuses_are_recomputable_without_event_details(self):
        statuses = ("passed", "failed", "unavailable", "indeterminate", "skipped")
        for number, status in enumerate(statuses, start=1):
            run_id = f"run-five-state-{number}"
            self._append(run_id, "source", "passed", 1)
            self._append(run_id, "compiler", status, 2)

        summaries = self.projection.list_runs(limit=10)
        self.assertEqual({item["status"] for item in summaries}, set(statuses))
        self.assertEqual(self.projection.list_runs(limit=1, status="failed")[0]["status"], "failed")
        compiler = self.projection.lifecycle(limit=10)[1]
        self.assertEqual(compiler["recorded_runs"], 5)
        self.assertEqual(compiler["not_reached_runs"], 0)
        self.assertEqual(compiler["status_counts"], {status: 1 for status in sorted(statuses)})
        coverage = self.projection.governance_coverage(limit=10)
        self.assertEqual(coverage["run_count"], 5)
        self.assertEqual(coverage["stages"][2]["not_reached_runs"], 5)
        detail = self.projection.run("run-five-state-1")
        self.assertNotIn("details", detail["events"][0])
        self.assertNotIn(self.temp.name, str(detail))

    def test_lifecycle_and_coverage_use_the_same_recent_run_window_as_run_list(self):
        self._append("run-a-old", "source", "failed", 1, occurred_at="2026-01-01T00:00:00+00:00")
        self._append("run-z-new", "source", "skipped", 1, occurred_at="2026-07-01T00:00:00+00:00")

        run = self.projection.list_runs(limit=1)[0]
        lifecycle_source = self.projection.lifecycle(limit=1)[0]
        coverage_source = self.projection.governance_coverage(limit=1)["stages"][0]

        self.assertEqual(run["run_id"], "run-z-new")
        self.assertEqual(lifecycle_source["run_count"], 1)
        self.assertEqual(lifecycle_source["status_counts"]["skipped"], 1)
        self.assertEqual(lifecycle_source["status_counts"]["failed"], 0)
        self.assertEqual(coverage_source, lifecycle_source)


if __name__ == "__main__":
    unittest.main()
