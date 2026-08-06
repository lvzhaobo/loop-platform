"""Phase 2 Compiler、Delivery 与 Adapter Registry 的离线回归测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from adapters.registry import list_adapters, load_adapter
from engine.compilers import list_compilers, load_compiler
from pipeline.delivery import list_deliveries, load_delivery


class TestRegistries(unittest.TestCase):
    def test_known_components_are_loadable(self):
        self.assertTrue({"simple", "mumuspec"}.issubset(list_compilers()))
        self.assertIn("local_artifact", list_deliveries())
        self.assertIn("local_queue", list_adapters())
        self.assertEqual(load_compiler("simple").name, "simple")
        self.assertEqual(load_delivery("local_artifact").name, "local_artifact")
        self.assertEqual(load_adapter("local_queue").source, "local")

    def test_unknown_components_fail_explicitly(self):
        for loader in (load_compiler, load_delivery, load_adapter):
            with self.assertRaises(ValueError):
                loader("does-not-exist")


if __name__ == "__main__":
    unittest.main()
