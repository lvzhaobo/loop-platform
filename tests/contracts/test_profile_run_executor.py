"""fixture-local Adapter 执行闭环的离线回归测试。"""

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from adapters.base import Task
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.paths import PlatformPaths
from engine.core.profiles import ProfileError, load_profile
from engine.core.run_executor import ProfileRunExecutor


class RecordingAdapter:
    def __init__(self, tasks):
        self.tasks = tasks
        self.reports = []

    def list_pending(self):
        return self.tasks

    def report(self, task_id, status, **fields):
        self.reports.append({"task_id": task_id, "status": status, "fields": fields})


class TestProfileRunExecutor(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile("fixture-local")
        self.task = Task(
            id="fixture-pomodoro", title="离线番茄钟参考需求", source="local",
            case="pomodoro", spec_text="构建一个离线番茄钟", priority=1,
            profile_id="fixture-local",
        )

    @staticmethod
    def _stores(directory):
        evidence = EvidenceStore(Path(directory) / "evidence")
        return evidence, EventStore(Path(directory) / "events", evidence_store=evidence)

    def test_fixture_run_persists_verified_events_and_reports_lifecycle(self):
        adapter = RecordingAdapter([self.task])
        with tempfile.TemporaryDirectory() as directory:
            evidence, events = self._stores(directory)
            plans = Path(directory) / "plans"
            output = Path(directory) / "output"
            with (patch("engine.core.run_executor.create_source_adapter", return_value=adapter),
                  patch.object(PlatformPaths, "RUN_PLANS_DIR", plans),
                  patch.object(PlatformPaths, "OUTPUT_DIR", output),
                  patch("engine.compilers.simple.subprocess.run") as process):
                result = ProfileRunExecutor(evidence, events).execute("fixture-local")[0]

            process.assert_not_called()
            self.assertEqual(result.status, "passed")
            self.assertEqual(result.event_count, 5)
            self.assertEqual([item["status"] for item in adapter.reports], ["running", "done"])
            final = adapter.reports[-1]["fields"]
            self.assertEqual(final["run_id"], result.run_id)
            self.assertEqual(final["plan_digest"], result.plan_digest)
            self.assertTrue(final["artifact_digest"])
            self.assertEqual(final["check_status"], "passed")
            self.assertEqual(final["delivery"]["status"], "passed")
            self.assertEqual(final["delivery"]["location"], "<local-path>")

            replay = events.replay(result.run_id)
            self.assertTrue(replay["verified"])
            self.assertEqual([event["stage"] for event in replay["events"]],
                             ["source", "compiler", "maker", "checker", "delivery"])
            self.assertNotIn(str(output), json.dumps(replay, ensure_ascii=False))
            self.assertTrue((plans / f"{result.run_id}.json").is_file())
            self.assertTrue((output / f"maker-{result.run_id}" / "delivery_plan.json").is_file())

    def test_maker_failure_reports_once_as_terminal_and_blocks_delivery(self):
        adapter = RecordingAdapter([self.task])
        with tempfile.TemporaryDirectory() as directory:
            evidence, events = self._stores(directory)
            with (patch("engine.core.run_executor.create_source_adapter", return_value=adapter),
                  patch.object(PlatformPaths, "RUN_PLANS_DIR", Path(directory) / "plans"),
                  patch.object(PlatformPaths, "OUTPUT_DIR", Path(directory) / "output"),
                  patch("engine.core.run_executor.make_with_context", side_effect=RuntimeError("maker unavailable"))):
                result = ProfileRunExecutor(evidence, events).execute("fixture-local")[0]

            self.assertEqual(result.status, "failed")
            self.assertEqual([item["status"] for item in adapter.reports], ["running", "failed"])
            self.assertEqual(adapter.reports[-1]["fields"]["check_status"], "failed")
            replay = events.replay(result.run_id)
            self.assertEqual([event["stage"] for event in replay["events"]], ["source", "compiler", "maker"])
            self.assertEqual(replay["status"], "failed")

    def test_execute_plan_uses_the_existing_frozen_identity_without_creating_a_second_plan(self):
        adapter = RecordingAdapter([self.task])
        with tempfile.TemporaryDirectory() as directory:
            evidence, events = self._stores(directory)
            plans = Path(directory) / "plans"
            output = Path(directory) / "output"
            with (patch("engine.core.run_executor.create_source_adapter", return_value=adapter),
                  patch.object(PlatformPaths, "RUN_PLANS_DIR", plans),
                  patch.object(PlatformPaths, "OUTPUT_DIR", output),
                  patch("engine.compilers.simple.subprocess.run") as process):
                from engine.core.profiles import create_run_plan, persist_run_plan
                frozen = create_run_plan(self.profile, {
                    "id": self.task.id, "title": self.task.title, "source": self.task.source,
                    "case": self.task.case, "priority": self.task.priority,
                    "spec_text": self.task.spec_text, "extra": self.task.extra,
                })
                persist_run_plan(frozen)
                result = ProfileRunExecutor(evidence, events).execute_plan(frozen.id)

            process.assert_not_called()
            self.assertEqual(result.run_id, frozen.run_id)
            self.assertEqual(result.plan_digest, frozen.digest)
            self.assertEqual(sorted(path.name for path in plans.glob("*.json")), [f"{frozen.id}.json"])
            self.assertEqual(adapter.reports[-1]["fields"]["plan_digest"], frozen.digest)

    def test_rejects_no_task_unknown_adapter_and_non_positive_limit_before_work(self):
        empty = RecordingAdapter([])
        with patch("engine.core.run_executor.create_source_adapter", return_value=empty):
            with self.assertRaisesRegex(ProfileError, "没有待执行任务"):
                ProfileRunExecutor().execute("fixture-local")
        self.assertEqual(empty.reports, [])

        bad_profile = replace(self.profile, source="missing_adapter")
        with patch("engine.core.run_executor.load_profile", return_value=bad_profile):
            with self.assertRaisesRegex(ProfileError, "未知 Adapter"):
                ProfileRunExecutor().execute("fixture-local")
        with self.assertRaisesRegex(ProfileError, "max_tasks"):
            ProfileRunExecutor().execute("fixture-local", max_tasks=0)

    def test_rejects_task_bound_to_another_profile_before_recording_a_run(self):
        adapter = RecordingAdapter([replace(self.task, profile_id="api-batch")])
        with tempfile.TemporaryDirectory() as directory:
            events = EventStore(Path(directory) / "events", evidence_store=EvidenceStore(Path(directory) / "evidence"))
            with (patch("engine.core.run_executor.create_source_adapter", return_value=adapter),
                  patch.object(PlatformPaths, "RUN_PLANS_DIR", Path(directory) / "plans")):
                with self.assertRaisesRegex(ProfileError, "未绑定到 Profile fixture-local"):
                    ProfileRunExecutor(event_store=events).execute("fixture-local", task_id=self.task.id)

            self.assertEqual(adapter.reports, [])
            self.assertFalse((Path(directory) / "events").exists())
            self.assertFalse((Path(directory) / "plans").exists())


if __name__ == "__main__":
    unittest.main()
