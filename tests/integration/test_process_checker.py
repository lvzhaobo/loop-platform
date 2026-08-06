"""集成测试: ProcessChecker run_id 绑定与证据边界 (F4)

使用 fixtures/findings_sample.json 模拟 BH 产物。
不依赖 API key / Node.js / Better Harness CLI。
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.checkers.process import ProcessChecker
from engine.checkers.base import CheckerResult


FIXTURE_FINDINGS = os.path.join(
    os.path.dirname(__file__), "..", "..", "fixtures", "findings_sample.json"
)


class TestProcessCheckerWithFixture(unittest.TestCase):
    """使用受控 fixture 测试 ProcessChecker 证据边界"""

    def setUp(self):
        self.checker = ProcessChecker()
        # 创建临时目录，模拟 BH 产物结构
        self.tmp = tempfile.mkdtemp(prefix="loop_test_")
        self.bh_dir = os.path.join(self.tmp, ".qoder", "better-harness")
        os.makedirs(os.path.join(self.bh_dir, "2026-08-06", "100000"), exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_findings(self, data: dict, run_id: str = ""):
        """写入 findings.json 并标记 run_id"""
        fp = os.path.join(self.bh_dir, "2026-08-06", "100000", "findings.json")
        d = dict(data)
        if run_id:
            d["run_id"] = run_id
        with open(fp, "w") as f:
            json.dump(d, f)
        return fp

    # ── 证据缺失 → unavailable ──

    def test_no_findings_unavailable(self):
        """无 findings.json 时结果应为 unavailable"""
        r = self.checker.check(self.tmp, run_id="")
        ai_check = next((c for c in r.checks if c["name"] == "AI诊断"), None)
        self.assertIsNotNone(ai_check)
        self.assertEqual(ai_check["status"], "unavailable")
        self.assertFalse(ai_check["pass"])
        self.assertIn("无 run_id 绑定", ai_check["detail"])

    # ── run_id 显式绑定 ──

    def test_run_id_binding_found(self):
        """指定 run_id 时仅匹配该报告"""
        with open(FIXTURE_FINDINGS) as f:
            fixture_data = json.load(f)
        self._write_findings(fixture_data, run_id="fixture-test-001")
        r = self.checker.check(self.tmp, run_id="fixture-test-001")
        ai_check = next((c for c in r.checks if c["name"] == "AI诊断"), None)
        self.assertIsNone(ai_check, "有匹配报告时不应出现 AI诊断 unavailable")
        # 应有五维度检查项
        dims = [c for c in r.checks if c["name"].startswith("流程:")]
        self.assertEqual(len(dims), 5, f"应包含 5 个维度检查项，实际 {len(dims)}")

    def test_run_id_no_match_unavailable(self):
        """指定不存在的 run_id 时返回 unavailable"""
        r = self.checker.check(self.tmp, run_id="nonexistent-999")
        ai_check = next((c for c in r.checks if c["name"] == "AI诊断"), None)
        self.assertIsNotNone(ai_check)
        self.assertEqual(ai_check["status"], "unavailable")
        self.assertIn("nonexistent-999", ai_check["detail"])

    # ── status 字段完整性 ──

    def test_findings_all_checks_have_status(self):
        """所有 findings 检查项有 status 字段"""
        with open(FIXTURE_FINDINGS) as f:
            fixture_data = json.load(f)
        self._write_findings(fixture_data, run_id="fixture-test-001")
        r = self.checker.check(self.tmp, run_id="fixture-test-001")
        for c in r.checks:
            self.assertIn("status", c, f"检查项 '{c['name']}' 缺少 status 字段")

    def test_five_dimensions_status(self):
        """五维度评分 status 与 pass 一致"""
        with open(FIXTURE_FINDINGS) as f:
            fixture_data = json.load(f)
        self._write_findings(fixture_data, run_id="fixture-test-001")
        r = self.checker.check(self.tmp, run_id="fixture-test-001")
        for c in r.checks:
            if c["name"].startswith("流程:"):
                self.assertEqual(c["status"],
                                 "passed" if c["pass"] else "failed",
                                 f"{c['name']} status 与 pass 不一致")

    def test_vulnerability_status(self):
        """流程漏洞：有 High 时应为 failed"""
        with open(FIXTURE_FINDINGS) as f:
            fixture_data = json.load(f)
        self._write_findings(fixture_data, run_id="fixture-test-001")
        r = self.checker.check(self.tmp, run_id="fixture-test-001")
        vuln = next((c for c in r.checks if c["name"] == "流程漏洞"), None)
        self.assertIsNotNone(vuln)
        self.assertEqual(vuln["status"], "failed", "有 High 漏洞时 status 应为 failed")
        self.assertFalse(vuln["pass"])

    # ── 跨任务不泄露 ──

    def test_no_cross_task_leakage(self):
        """run_id A 不会消费 run_id B 的报告"""
        import copy
        with open(FIXTURE_FINDINGS) as f:
            data_a = json.load(f)
        data_b = copy.deepcopy(data_a)
        data_b["summary"]["dimensions"][0]["score"] = 42  # 故意改低

        # 写入两个 run_id 的报告
        self._write_findings(data_a, run_id="task-a")
        fp_b = os.path.join(self.bh_dir, "2026-08-06", "100001", "findings.json")
        os.makedirs(os.path.dirname(fp_b), exist_ok=True)
        data_b["run_id"] = "task-b"
        with open(fp_b, "w") as f:
            json.dump(data_b, f)

        r = self.checker.check(self.tmp, run_id="task-a")
        target_understanding = next(
            (c for c in r.checks if c["name"] == "流程:目标清晰度"), None
        )
        self.assertIsNotNone(target_understanding)
        self.assertIn("85/100", target_understanding["detail"],
                      f"应匹配 task-a 的 85 分，而非 task-b 的 42 分")

    # ── 不产生副作用 ──

    def test_check_does_not_write_to_qoder(self):
        """check() 不写入 .qoder/ 目录"""
        before = set()
        qoder_dir = os.path.join(self.tmp, ".qoder")
        for root, dirs, files in os.walk(self.tmp):
            for f in files:
                before.add(os.path.join(root, f))

        r = self.checker.check(self.tmp, run_id="")

        after = set()
        for root, dirs, files in os.walk(self.tmp):
            for f in files:
                after.add(os.path.join(root, f))

        new_files = after - before
        self.assertEqual(len(new_files), 0,
                         f"check() 不应创建新文件: {new_files}")


class TestNegativeCase(unittest.TestCase):
    """负例测试：必须失败且不产生副作用"""

    def test_missing_manifest_fails(self):
        """fixture 没有 manifest.json 的目录 → engine/gate 应失败"""
        fixture_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "fixtures", "manifest_missing"
        )
        # 确保该目录存在且无 manifest
        self.assertTrue(os.path.isdir(fixture_dir))
        self.assertFalse(
            os.path.exists(os.path.join(fixture_dir, "spec", "manifest.json")),
            "负例 fixture 不应有 manifest.json"
        )

        # engine/generate.py 的 CASE 发现逻辑应跳过此目录
        from engine.generate import CASES
        self.assertNotIn("manifest_missing", CASES,
                         "无 manifest 的目录不应被识别为有效 case")


if __name__ == "__main__":
    unittest.main()
