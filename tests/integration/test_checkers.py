"""集成测试: Checker 注册、加载与执行 (F4)

不依赖 API key，所有测试离线。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.checkers import register, load_checker, list_checkers
from engine.checkers.base import CheckerResult

# F4: 确保所有 Checker 子类被 import 以触发 @register()
import engine.checkers.process  # noqa: F401
import engine.checkers.security  # noqa: F401
import engine.checkers.runtime   # noqa: F401
import engine.checkers.e2e       # noqa: F401


class TestCheckerRegistry(unittest.TestCase):
    """测试 Checker 注册与发现"""

    def test_registry_has_checkers(self):
        all_names = list_checkers()
        self.assertGreater(len(all_names), 0, "Checker 注册表不应为空")

    def test_known_checkers_exist(self):
        all_names = list_checkers()
        for expected in ["process", "security", "runtime", "e2e"]:
            self.assertIn(expected, all_names, f"{expected} checker 未注册")

    def test_load_checker_returns_instance(self):
        for name in list_checkers():
            c = load_checker(name)
            self.assertIsNotNone(c, f"load_checker({name}) 返回 None")
            self.assertEqual(c.name, name, f"loaded checker name 不匹配: {c.name} != {name}")

    def test_load_unknown_raises(self):
        with self.assertRaises(ValueError):
            load_checker("nonexistent_checker_xyz")


class TestCheckerExecution(unittest.TestCase):
    """测试所有 Checker 可正常执行（离线）"""

    def setUp(self):
        # 用 engine/ 作为测试目标目录
        self.target_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "engine"
        )

    def test_security_checker(self):
        c = load_checker("security")
        r = c.check(self.target_dir)
        self.assertIsInstance(r, CheckerResult)
        self.assertGreaterEqual(r.total_count, 0)
        self.assertIsInstance(r.summarize(), dict)

    def test_runtime_checker(self):
        c = load_checker("runtime")
        r = c.check(self.target_dir)
        self.assertIsInstance(r, CheckerResult)
        # runtime checker 可能跳过（无入口），但不应异常
        self.assertIsInstance(r.summarize(), dict)

    def test_e2e_checker(self):
        c = load_checker("e2e")
        r = c.check(self.target_dir)
        self.assertIsInstance(r, CheckerResult)
        self.assertIsInstance(r.summarize(), dict)

    def test_all_checker(self):
        """AllChecker 聚合所有检查"""
        from engine.checkers.all_checker import AllChecker
        c = AllChecker()
        r = c.check(self.target_dir)
        self.assertIsInstance(r, CheckerResult)
        self.assertGreater(r.total_count, 0)
        summary = r.summarize()
        self.assertIsInstance(summary, dict)


if __name__ == "__main__":
    unittest.main()
