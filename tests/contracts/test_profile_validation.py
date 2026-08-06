"""Profile 运行时 schema 边界测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.profiles import Profile, ProfileError, load_profile, validate_profile


class TestProfileValidation(unittest.TestCase):
    def setUp(self):
        self.raw = load_profile("fixture-local").to_dict()

    def test_unknown_profile_or_policy_field_is_rejected(self):
        with self.assertRaises(ProfileError):
            Profile.from_dict({**self.raw, "unexpected": True})
        with self.assertRaises(ProfileError):
            Profile.from_dict({**self.raw, "policy": {**self.raw["policy"], "unsafe": True}})

    def test_invalid_policy_values_are_rejected(self):
        raw = {**self.raw, "policy": {**self.raw["policy"], "max_attempts": 0}}
        with self.assertRaises(ProfileError):
            validate_profile(Profile.from_dict(raw))
        raw = {**self.raw, "policy": {**self.raw["policy"], "on_unavailable": "ignore"}}
        with self.assertRaises(ProfileError):
            validate_profile(Profile.from_dict(raw))


if __name__ == "__main__":
    unittest.main()
