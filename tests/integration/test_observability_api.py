"""Phase 4 只读 observability API 回归测试。"""
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import studio.server as studio_server
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import RunEvent
from engine.core.paths import PlatformPaths

DIGEST = "a" * 64
STAGE_DIGESTS = {
    "source": {"input": DIGEST},
    "compiler": {"input": DIGEST, "spec": DIGEST, "acceptance": DIGEST},
    "maker": {"input": DIGEST, "spec": DIGEST, "acceptance": DIGEST, "artifact": DIGEST},
    "checker": {"input": DIGEST, "spec": DIGEST, "acceptance": DIGEST, "artifact": DIGEST},
    "delivery": {"input": DIGEST, "spec": DIGEST, "acceptance": DIGEST, "artifact": DIGEST},
}


class TestObservabilityApi(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = EvidenceStore(self.root / "data" / "evidence")
        self.events = EventStore(self.root / "events", evidence_store=self.evidence)
        self.client = studio_server.app.test_client()
        self._write_run()

    def tearDown(self):
        self.temp.cleanup()

    def _append_event(self, run_id, sequence, stage, status="passed", *, occurred_at=None,
                      evidence_required=True, source=None):
        evidence = ()
        if evidence_required:
            evidence = (self.evidence.put_json(
                {"stage": stage}, source=source or stage, run_id=run_id,
                plan_digest=DIGEST, kind=f"{stage}-{sequence}"),)
        self.events.append(RunEvent(
            event_id=f"{run_id}-{sequence}", run_id=run_id, sequence=sequence,
            occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
            stage=stage, status=status, profile_ref="fixture-local@1",
            task_id="fixture-pomodoro", plan_digest=DIGEST,
            digests=STAGE_DIGESTS[stage], component_versions={"test": "1"},
            evidence=evidence,
        ))

    def _write_run(self):
        self.run_id = "run-api-001"
        for sequence, stage in enumerate(STAGE_DIGESTS, start=1):
            self._append_event(self.run_id, sequence, stage)

    def _paths(self):
        stack = ExitStack()
        stack.enter_context(patch.object(PlatformPaths, "RUN_EVENTS_DIR", self.root / "events"))
        stack.enter_context(patch.object(PlatformPaths, "DATA_DIR", self.root / "data"))
        return stack

    def _snapshot(self):
        return {
            str(path.relative_to(self.root)): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*") if path.is_file()
        }

    def test_run_lifecycle_and_coverage_are_verified_read_only_projections(self):
        before = self._snapshot()
        with self._paths():
            runs = self.client.get("/api/observability/runs")
            detail = self.client.get(f"/api/observability/runs/{self.run_id}")
            lifecycle = self.client.get("/api/observability/lifecycle")
            coverage = self.client.get("/api/observability/governance-coverage")
            blocked_write = self.client.post("/api/observability/lifecycle")
        self.assertEqual(runs.status_code, 200)
        summary = runs.get_json()["runs"][0]
        self.assertEqual(set(summary), {"run_id", "status", "integrity", "event_count", "last_occurred_at", "stage_statuses"})
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["integrity"], "verified")
        self.assertNotIn(str(self.root), str(summary))
        event = detail.get_json()["run"]["events"][-1]
        self.assertEqual(event["stage"], "delivery")
        self.assertNotIn("details", event)
        self.assertNotIn("profile_ref", event)
        self.assertNotIn("task_id", event)
        self.assertNotIn("plan_digest", event)
        self.assertNotIn("component_versions", event)
        self.assertNotIn("uri", event["evidence"][0])
        self.assertEqual(lifecycle.get_json()["stages"][0]["status_counts"]["passed"], 1)
        body = coverage.get_json()["coverage"]
        self.assertEqual(body["source"], "verified-event-projection")
        self.assertEqual(body["coverage_scope"], "evidence-backed-stage-coverage")
        self.assertTrue(body["limitations"])
        self.assertEqual(blocked_write.status_code, 405)
        self.assertEqual(before, self._snapshot())

    def test_tampered_payload_or_metadata_becomes_indeterminate(self):
        evidence = self.events.read(self.run_id)[0].evidence[0]
        payload = self.evidence.root / self.run_id / f"{evidence.id}.bin"
        payload.write_bytes(b"tampered")
        with self._paths():
            response = self.client.get(f"/api/observability/runs/{self.run_id}")
        self.assertEqual(response.status_code, 200)
        run = response.get_json()["run"]
        self.assertEqual(run["status"], "indeterminate")
        self.assertEqual(run["events"][0]["status"], "indeterminate")

        metadata_run = "run-metadata-001"
        self._append_event(metadata_run, 1, "source")
        evidence = self.events.read(metadata_run)[0].evidence[0]
        metadata = self.evidence.root / metadata_run / f"{evidence.id}.json"
        metadata.write_text("{}", encoding="utf-8")
        with self._paths():
            response = self.client.get(f"/api/observability/runs/{metadata_run}")
        self.assertEqual(response.get_json()["run"]["integrity"], "indeterminate")

    def test_missing_evidence_is_unavailable_and_latest_attempt_wins(self):
        failed_run = "run-failed"
        skipped_run = "run-skipped"
        no_evidence_run = "run-missing-evidence"
        self._append_event(failed_run, 1, "source", "failed")
        self._append_event(skipped_run, 1, "source", "skipped")
        self._append_event(no_evidence_run, 1, "source", "failed", evidence_required=False)
        self._append_event(self.run_id, 6, "checker", "failed")
        self._append_event(self.run_id, 7, "checker", "passed")
        with self._paths():
            failed = self.client.get(f"/api/observability/runs/{failed_run}").get_json()["run"]
            skipped = self.client.get(f"/api/observability/runs/{skipped_run}").get_json()["run"]
            missing = self.client.get(f"/api/observability/runs/{no_evidence_run}").get_json()["run"]
            lifecycle = self.client.get("/api/observability/lifecycle").get_json()["stages"]
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(missing["integrity"], "unavailable")
        self.assertEqual(missing["status"], "unavailable")
        checker = next(item for item in lifecycle if item["stage"] == "checker")
        self.assertEqual(checker["status_counts"]["passed"], 1)
        self.assertEqual(checker["status_counts"]["failed"], 0)
        self.assertEqual(sum(checker["status_counts"].values()), checker["recorded_runs"])

    def test_corrupt_and_illegal_run_files_are_isolated_from_other_runs(self):
        (self.events.root / "run-corrupt.jsonl").write_text("not-json\n", encoding="utf-8")
        (self.events.root / "bad run.jsonl").write_text("not-json\n", encoding="utf-8")
        with self._paths():
            runs = self.client.get("/api/observability/runs").get_json()["runs"]
            stages = self.client.get("/api/observability/lifecycle").get_json()["stages"]
        self.assertIn("run-corrupt", [item["run_id"] for item in runs])
        self.assertNotIn("bad run", [item["run_id"] for item in runs])
        source = next(item for item in stages if item["stage"] == "source")
        self.assertEqual(source["indeterminate_runs"], 1)
        self.assertEqual(source["recorded_runs"] + source["not_reached_runs"] + source["indeterminate_runs"],
                         source["run_count"])
        self.assertEqual(sum(source["status_counts"].values()), source["recorded_runs"])

    def test_runs_are_sorted_by_event_time_and_invalid_query_is_rejected(self):
        self._append_event("run-sort-early", 1, "source", occurred_at="2026-01-01T00:00:00+00:00")
        self._append_event("run-sort-late", 1, "source", occurred_at="2026-07-01T00:00:00+00:00")
        with self._paths():
            response = self.client.get("/api/observability/runs")
            invalid_status = self.client.get("/api/observability/runs?status=unknown")
            invalid_limit = self.client.get("/api/observability/runs?limit=not-a-number")
            missing = self.client.get("/api/observability/runs/run-does-not-exist")
        ids = [item["run_id"] for item in response.get_json()["runs"]]
        self.assertLess(ids.index("run-sort-late"), ids.index("run-sort-early"))
        self.assertEqual(invalid_status.status_code, 400)
        self.assertEqual(invalid_limit.status_code, 400)
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
