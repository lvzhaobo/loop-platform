"""Phase 2/3 Registry、Profile 与 Run Plan 的离线回归测试。"""

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.paths import PlatformPaths
from engine.core.profiles import (ProfileError, create_run_plan, get_run_plan,
                                  list_profiles, list_run_plans, load_profile,
                                  persist_run_plan, run_context, validate_profile)


class TestProfileAndRunPlan(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile("fixture-local")
        self.task = {"id": "fixture-task", "title": "Fixture task", "source": "local", "case": "pomodoro"}

    def test_fixture_local_profile_is_valid(self):
        validate_profile(self.profile)
        self.assertEqual(self.profile.ref, "fixture-local@1")
        self.assertFalse(self.profile.policy["allow_network"])
        self.assertIn("fixture-local", [item["id"] for item in list_profiles() if item.get("valid")])

    def test_reference_profiles_replace_exactly_one_component(self):
        baseline = self.profile.to_dict()
        expectations = {
            "api-batch": {"maker": "deepseek"},
            "mumuspec-local": {"compiler": "mumuspec"},
        }
        valid_ids = {item["id"] for item in list_profiles() if item.get("valid")}

        for profile_id, expected_change in expectations.items():
            profile = load_profile(profile_id)
            validate_profile(profile)
            content = profile.to_dict()
            self.assertEqual(profile.ref, f"{profile_id}@1")
            self.assertIn(profile_id, valid_ids)
            changed = {
                key: value for key, value in content.items()
                if key not in {"id", "description"} and value != baseline[key]
            }
            self.assertEqual(changed, expected_change)

    def test_publish_or_deploy_profile_is_rejected(self):
        unsafe = replace(self.profile, policy={**self.profile.policy, "allow_publish": True})
        with self.assertRaises(ProfileError):
            validate_profile(unsafe)

    def test_run_plan_is_immutable_when_persisted(self):
        plan = create_run_plan(self.profile, self.task)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(PlatformPaths, "RUN_PLANS_DIR", Path(directory)):
                target = persist_run_plan(plan)
                self.assertTrue(target.is_file())
                self.assertEqual(get_run_plan(plan.id)["digest"], plan.digest)
                self.assertEqual(list_run_plans()[0]["id"], plan.id)
                with self.assertRaises(ProfileError):
                    persist_run_plan(plan)

    def test_run_context_preserves_frozen_identifiers(self):
        plan = create_run_plan(self.profile, self.task)
        context = run_context(plan)
        self.assertEqual(context.run_id, plan.run_id)
        self.assertEqual(context.profile, "fixture-local@1")
        self.assertEqual(context.hashes["plan"], plan.digest)
