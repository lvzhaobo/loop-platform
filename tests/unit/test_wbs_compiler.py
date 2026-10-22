"""WBS 编译层单测：钉住三类实测踩过的解析坑。

用例都写成最小内联样本，不依赖 cases/ 里的真实文档——cases/ 与 data/ 不入仓，
拿它当 fixture 会让测试在别人克隆的仓库里直接失效。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine", "tools"))

import wbs_compiler as w  # noqa: E402


class TestAcRefParsing(unittest.TestCase):
    """AC 编号引用的边界。这三条对应 fs_002 告警曾经完全不触发的原因。"""

    def test_non_breaking_hyphen_is_recognised(self):
        # fs_002 用的是 U+2011 不换行连字符，肉眼与 ASCII 减号无差别
        self.assertEqual(w.AC_REF_RE.findall("所有验收条件（AC\u2011001 至 AC\u2011008）"), ["1", "8"])

    def test_cjk_neighbourhood_does_not_block_matching(self):
        # '1' 与 '到'、'到' 与 'A' 在 Python 眼里都是 \w，用 \b 锚定会漏掉后半条引用
        self.assertEqual(w.AC_REF_RE.findall("AC01到AC08"), ["1", "8"])
        self.assertTrue(w.AC_RANGE_RE.search("AC01到AC08"))

    def test_hyphen_with_spaces_and_plain_forms(self):
        self.assertEqual(w.AC_REF_RE.findall("AC - 7"), ["7"])
        self.assertEqual(w.AC_REF_RE.findall("AC-001"), ["1"])
        self.assertEqual(w.AC_REF_RE.findall("AC_3"), ["3"])

    def test_prefixed_word_is_not_a_reference(self):
        self.assertEqual(w.AC_REF_RE.findall("MAC1"), [])

    def test_tc_id_alone_is_not_treated_as_ac_reference(self):
        self.assertEqual(w.AC_REF_RE.findall("TC1 未通过"), [])


class TestPlanParsing(unittest.TestCase):
    """四种 12-plan 形态都要能抽出任务，一种失败不影响其他。"""

    def test_milestone_table_with_semantic_header_names(self):
        md = ("| 里程碑 | 主要交付物 | 完成标准 |\n"
              "|---|---|---|\n"
              "| M3 – 集成测试通过 | 测试套件 | AC\u2011001 至 AC\u2011008 通过 |\n")
        tasks = w.parse_plan(md)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], "M3")
        self.assertEqual(tasks[0]["ac_refs"], [1, 8])
        self.assertTrue(tasks[0]["ac_range"])

    def test_milestone_id_without_title_or_separator(self):
        # 单元格只写 “M2”：要分隔符会静默丢掉整个里程碑
        md = ("| 阶段 | 主要交付物 |\n|---|---|\n| M2 | `/pause` API |\n"
              "| M4：发布 | 镜像 |\n")
        self.assertEqual([t["id"] for t in w.parse_plan(md)], ["M2", "M4"])

    def test_ordered_list_milestones(self):
        md = "## 里程碑\n1. 静态页面 + 计时逻辑\n2. 音效与持久化\n"
        tasks = w.parse_plan(md)
        self.assertEqual([t["id"] for t in tasks], ["M1", "M2"])

    def test_role_grouped_task_breakdown(self):
        md = ("## 关键任务分解\n- **后端**\n  - 实现 /api/health 探针\n"
              "- **前端**\n  - 列表页渲染\n")
        tasks = w.parse_plan(md)
        self.assertEqual({t["role"] for t in tasks}, {"后端", "前端"})

    def test_bullets_outside_guarded_sections_are_not_tasks(self):
        md = "## 背景\n- 这是一句说明，不是任务\n"
        self.assertEqual(w.parse_plan(md), [])


class TestRouteExtraction(unittest.TestCase):
    def test_only_backticked_paths_count(self):
        # "Selenium/Cypress"、"macOS/Linux" 不是接口；错报会把工具结论整体拖成不可信
        self.assertEqual(w.extract_routes("用 Selenium/Cypress 覆盖 macOS/Linux"), set())
        self.assertEqual(w.extract_routes("提供 `/playback/play` 与 `/pause`"),
                         {"/playback/play", "/pause"})

    def test_clean_does_not_starve_route_detection(self):
        # 落盘的 deliverables 已剥反引号，路径识别必须靠 raw 原文
        md = ("| 阶段 | 时间 | 目标 | 主要交付物 |\n"
              "|---|---|---|---|\n"
              "| M2 | 第 2 周 | 播放控制 | `/pause` API |\n")
        task = w.parse_plan(md)[0]
        self.assertEqual(task["id"], "M2")
        self.assertNotIn("`", " ".join(task["deliverables"]))
        self.assertIn("/pause", w.extract_routes(task["raw"]))


class TestClean(unittest.TestCase):
    def test_paired_marks_are_stripped_not_just_edges(self):
        # 反引号只有一侧在首尾时，按首尾字符剥会剩半个标记漏进产物
        self.assertEqual(w.clean("`/pause` API"), "/pause API")
        self.assertEqual(w.clean("**M2：核心播放**"), "M2：核心播放")
        self.assertEqual(w.clean("  普通文字 "), "普通文字")


class TestFindings(unittest.TestCase):
    def test_uncovered_ac_is_reported_not_silently_dropped(self):
        tasks = [{"id": "M1", "milestone": "M1", "title": "首页", "level": "milestone",
                  "week": None, "goal": "", "role": "", "deliverables": ["index.html"],
                  "done_criteria": "", "ac_refs": [], "ac_range": False, "raw": "首页"}]
        acs = [{"id": "TC1", "type": "file_exists", "file": "index.html"},
               {"id": "TC2", "type": "http_status", "route": "/missing"}]
        findings = w.relate(tasks, acs)
        self.assertEqual([a["id"] for a in findings["uncovered_ac"]], ["TC2"])
        self.assertEqual(tasks[0]["covers_ac"], ["TC1"])
        self.assertTrue(tasks[0]["auto_verifiable"])

    def test_manual_ac_coverage_is_flagged_as_dangling(self):
        tasks = [{"id": "M1", "milestone": "M1", "title": "登录页检查", "level": "milestone",
                  "week": None, "goal": "", "role": "", "deliverables": ["登录页检查"],
                  "done_criteria": "", "ac_refs": [], "ac_range": False, "raw": "登录页检查"}]
        acs = [{"id": "TC1", "type": "manual", "needle": "登录页检查"}]
        findings = w.relate(tasks, acs)
        self.assertEqual(tasks[0]["covers_ac"], ["TC1"])
        self.assertFalse(tasks[0]["auto_verifiable"])
        self.assertEqual([a["id"] for a in findings["dangling_ac"]], ["TC1"])

    def test_declaration_mismatch_surfaces(self):
        # 计划假定 8 条、契约只有 6 条，且编号 8 在契约里不存在
        tasks = [{"id": "M3", "ac_refs": [1, 8], "ac_range": True}]
        md = "所有验收条件（AC\u2011001 至 AC\u2011008）通过"
        acs = [{"id": f"TC{i}"} for i in range(1, 7)]
        decl = w.check_ac_declaration(tasks, acs, md)
        self.assertEqual(decl["plan_assumes_count"], 8)
        self.assertEqual(decl["contract_ac_count"], 6)
        self.assertEqual(decl["contract_id_style"], ["TCN"])
        self.assertEqual(decl["refs_absent_from_contract"], [8])

    def test_no_reference_returns_none(self):
        self.assertIsNone(w.check_ac_declaration([{"ac_refs": []}], [{"id": "TC1"}], "没有引用"))


if __name__ == "__main__":
    unittest.main()
