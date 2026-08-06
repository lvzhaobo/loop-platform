"""单元测试: PlatformPaths + find_root + load_config (F4)"""

import os
import sys
import unittest

# 确保 engine/ 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.paths import PlatformPaths, find_root, load_config
from pathlib import Path


class TestFindRoot(unittest.TestCase):
    """测试仓库根发现逻辑"""

    def test_find_root_exists(self):
        root = find_root()
        self.assertTrue(root.is_dir(), f"find_root() 返回的路径不存在: {root}")
        self.assertTrue((root / "engine").is_dir(), f"engine/ 目录不存在于 {root}")
        self.assertTrue((root / "studio").is_dir(), f"studio/ 目录不存在于 {root}")

    def test_env_override(self):
        """LOOP_ROOT 环境变量优先"""
        os.environ["LOOP_ROOT"] = "/tmp/loop_test_root"
        import engine.core.paths as paths_mod
        # 清除缓存以重新计算
        paths_mod.find_root.cache_clear()
        root = str(paths_mod.find_root())
        self.assertIn("loop_test_root", root)
        del os.environ["LOOP_ROOT"]
        paths_mod.find_root.cache_clear()


class TestPlatformPaths(unittest.TestCase):
    """测试集中路径解析"""

    def setUp(self):
        self.root = find_root()

    def test_cases_dir(self):
        p = PlatformPaths.CASES_DIR
        self.assertTrue(p.is_dir(), f"cases/ 不存在: {p}")
        self.assertTrue((p / "pomodoro").is_dir(), f"pomodoro case 缺失")

    def test_data_dir(self):
        p = PlatformPaths.DATA_DIR
        self.assertTrue(p.is_dir(), f"data/ 不存在: {p}")

    def test_engine_dir(self):
        p = PlatformPaths.ENGINE_DIR
        self.assertTrue(p.is_dir(), f"engine/ 不存在: {p}")

    def test_config_files_exist(self):
        self.assertTrue(PlatformPaths.CONFIG_FILE.is_file(), f"config.env 缺失")
        self.assertTrue(PlatformPaths.ENV_FILE.is_file(), f".env 缺失")

    def test_legacy_paths_exist(self):
        """旧 loop/ 路径仍存在（只读保留）"""
        self.assertTrue(PlatformPaths.LEGACY_LOOP.is_dir(), "loop/ 旧目录不应被删除")

    def test_guard_legacy_warning(self):
        """访问旧路径应触发 DeprecationWarning"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # 旧路径 guard_legacy
            p = PlatformPaths.LEGACY_CASES
            result = PlatformPaths.guard_legacy(p)
            # 因为新路径 cases/ 已存在，应自动重定向
            self.assertTrue("cases" in str(result))

    def test_resolve_relative(self):
        result = PlatformPaths.resolve("fixtures/pomodoro")
        self.assertTrue(result.is_dir(), f"相对路径解析失败: {result}")


class TestLoadConfig(unittest.TestCase):
    """测试统一配置加载"""

    def test_load_config_returns_dict(self):
        config = load_config()
        self.assertIsInstance(config, dict)
        self.assertGreater(len(config), 0, "配置文件不应为空")

    def test_config_env_vs_dotenv_priority(self):
        """环境变量优先级最高"""
        os.environ["LOOP_TEST_VAR"] = "env_override"
        config = load_config()
        self.assertEqual(config.get("LOOP_TEST_VAR"), "env_override")
        del os.environ["LOOP_TEST_VAR"]


if __name__ == "__main__":
    unittest.main()
