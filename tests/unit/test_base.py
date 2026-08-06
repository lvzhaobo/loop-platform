"""单元测试: CheckStatus + status_from_bool + CheckerResult (F4)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.checkers.base import (
    CheckerResult,
    status_from_bool,
)


class TestStatusFromBool(unittest.TestCase):
    """测试 status_from_bool 五态转换"""

    def test_passed(self):
        self.assertEqual(status_from_bool(True), "passed")

    def test_failed(self):
        self.assertEqual(status_from_bool(False), "failed")

    def test_indeterminate(self):
        self.assertEqual(status_from_bool(False, indeterminate=True), "indeterminate")
        # indeterminate 优先级高于 failed
        self.assertEqual(status_from_bool(True, indeterminate=True), "passed")

    def test_skipped(self):
        self.assertEqual(status_from_bool(False, skipped=True), "skipped")
        # skipped 优先级最高
        self.assertEqual(status_from_bool(True, skipped=True), "passed")


class TestCheckerResult(unittest.TestCase):
    """测试 CheckerResult 和 summarize"""

    def test_empty_result(self):
        r = CheckerResult()
        self.assertEqual(r.pass_count, 0)
        self.assertEqual(r.total_count, 0)
        self.assertFalse(r.all_pass)
        self.assertEqual(r.summarize(), {})

    def test_mixed_status(self):
        checks = [
            {"name": "a", "pass": True, "status": "passed"},
            {"name": "b", "pass": False, "status": "failed"},
            {"name": "c", "pass": False, "status": "unavailable"},
        ]
        r = CheckerResult(pass_count=1, total_count=3, checks=checks, all_pass=False)
        s = r.summarize()
        self.assertEqual(s, {"passed": 1, "failed": 1, "unavailable": 1})

    def test_legacy_no_status_field(self):
        """旧格式检查项（无 status 字段）从 pass 推断"""
        checks = [
            {"name": "x", "pass": True},
            {"name": "y", "pass": False},
        ]
        r = CheckerResult(pass_count=1, total_count=2, checks=checks)
        s = r.summarize()
        self.assertEqual(s["passed"], 1)
        self.assertEqual(s["failed"], 1)


if __name__ == "__main__":
    unittest.main()
