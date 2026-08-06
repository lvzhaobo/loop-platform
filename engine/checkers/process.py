"""流程质量 Checker。调用 Better Harness CLI 收集静态证据，读取 AI 生成的 findings.json。

两层架构:
    Layer 1 - 静态证据（always available）: 项目规模、依赖健康度、工作区漂移、会话可用性
    Layer 2 - AI 诊断（需先运行 /better-harness skill）: 五维度评分 + 优先级漏洞清单

F5 证据边界：
    - 五项统一状态（passed/failed/unavailable/indeterminate/skipped）
    - run_id 显式绑定，禁止跨任务"最新报告"猜测
    - Loop heuristic（CLI 证据 + 本 checker 自身）不写入 .qoder/better-harness/
    - 无 BH 证据时结果为 unavailable，绝不伪装为 passed

用法:
    from checkers.process import ProcessChecker
    checker = ProcessChecker()
    result = checker.check(target_dir="output/maker-xxx", run_id="20260806-abc123")
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from .base import Checker, CheckerResult, CheckStatus, status_from_bool
from . import register

# Better Harness CLI 路径（Qoder 插件缓存）
# F5: 该 CLI 只读取状态、输出到 stdout，不写入 .qoder/better-harness/ 目录
_BH_ROOT = os.path.expanduser(
    "~/.qoder/plugins/cache/qoder-bundler/better-harness"
)
_BH_CLI = os.path.join(_BH_ROOT, "scripts", "better-harness.mjs")
_NODE = "node"

# 五维度标签
_DIM_LABELS = {
    "task-understanding":     "目标清晰度",
    "controlled-execution":   "执行可控性",
    "change-validation":      "变更验证",
    "reliable-delivery":      "交付可靠性",
    "learning-capture":       "经验沉淀",
}

# P1-7: 五维度评分阈值（暂硬编码，后续可迁入 config.env）
_SCORE_THRESHOLD = 60


@register("process")
class ProcessChecker(Checker):
    """Better Harness 流程质量评估器。F5: 所有检查项强制带 status 字段。"""

    name = "process"

    # ── Layer 1: 静态证据（CLI，无 AI 依赖，不写磁盘） ──

    def _run_cli_evidence(self, target_dir: str) -> dict | None:
        """运行 better-harness report --json，返回静态证据。
        
        F5: 明确标注该调用只读取状态并输出到 stdout，不写入 .qoder/better-harness/。
        CLI 不可用时返回 None。
        """
        if not os.path.isfile(_BH_CLI):
            return None
        # 检查 Node.js 可用性
        try:
            node_check = subprocess.run(
                [_NODE, "--version"], capture_output=True, timeout=5,
            )
            if node_check.returncode != 0:
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        try:
            # --json 输出到 stdout，不写任何文件
            proc = subprocess.run(
                [_NODE, _BH_CLI, "report", "--json", "--cwd", target_dir],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode == 0:
                return json.loads(proc.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass
        return None

    # ── Layer 2: AI 诊断（需先运行 /better-harness skill） ──
    # F5: 改为 run_id 显式绑定，不再按"最新"猜测

    def _find_findings(self, target_dir: str, *, run_id: str = "") -> dict | None:
        """查找指定 run_id 的 findings.json（AI skill 生成）。
        
        F5 变更:
            - 当 run_id 提供时：仅匹配该 run_id 的报告（按 findings 内 run_id/meta 字段）
            - 当 run_id 为空时：回退到无绑定查找（但 check() 层会标记 unavailable）
            - Loop heuristic 自身的检查结果绝不写入 .qoder/better-harness/
        """
        search_root = os.path.abspath(target_dir) if target_dir else os.getcwd()
        bh_dir = os.path.join(search_root, ".qoder", "better-harness")
        if not os.path.isdir(bh_dir):
            return None

        candidates: list[tuple[str, str]] = []  # [(date/ts, filepath)]
        for date_dir in sorted(os.listdir(bh_dir), reverse=True):
            dp = os.path.join(bh_dir, date_dir)
            if not os.path.isdir(dp):
                continue
            for ts_dir in sorted(os.listdir(dp), reverse=True):
                fp = os.path.join(dp, ts_dir, "findings.json")
                if os.path.isfile(fp):
                    key = f"{date_dir}/{ts_dir}"
                    candidates.append((key, fp))

        if not candidates:
            return None

        # run_id 显式绑定：仅消费匹配该 run_id 的报告
        if run_id:
            for key, fp in candidates:
                try:
                    with open(fp, encoding="utf-8") as f:
                        data = json.load(f)
                    # 支持两种绑定方式：meta.run_id 或根级 run_id
                    meta_run = (data.get("meta") or {}).get("run_id", "")
                    root_run = data.get("run_id", "")
                    if meta_run == run_id or root_run == run_id:
                        return data
                except (json.JSONDecodeError, OSError):
                    continue
            # 未找到匹配 run_id 的报告
            return None

        # 无 run_id：取最新（由 check() 层决定是否标记 unavailable）
        best_key, best_fp = max(candidates, key=lambda x: x[0])
        try:
            with open(best_fp, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return None

    # ── 主入口 ──

    def check(self, target_dir: str, *, run_id: str = "") -> CheckerResult:
        """F5: 接受 run_id 显式绑定，run_id 为空时结果强制 unavailable。"""
        checks: list[dict] = []

        # Layer 2 优先：AI 诊断报告（绑定 run_id）
        findings = self._find_findings(target_dir, run_id=run_id) if run_id else None
        if findings:
            self._report_findings(checks, findings)
        else:
            # P0-1: 缺失证据 → unavailable，不伪装为通过
            detail_msg = "未找到 findings.json。"
            if not run_id:
                detail_msg += "无 run_id 绑定，跳过报告查找。"
            else:
                detail_msg += f"未找到 run_id={run_id} 的绑定报告。"
            checks.append({
                "name": "AI诊断",
                "pass": False,
                "status": "unavailable",
                "detail": detail_msg,
                "fix": "qodercli -w <project-dir> /better-harness",
            })

        # Layer 1 补充：CLI 静态证据（F5: 明确标注不写入 .qoder/）
        evidence = self._run_cli_evidence(target_dir)
        if evidence:
            self._report_evidence(checks, evidence)

        pass_count = sum(1 for c in checks if c["pass"])
        return CheckerResult(
            pass_count=pass_count, total_count=len(checks),
            checks=checks, all_pass=pass_count == len(checks),
        )

    # ── 报告生成 ──

    def _report_findings(self, checks: list[dict], findings: dict):
        """解析 AI 生成的 findings.json → Loop 检查项。F5: 所有项带 status。"""
        s = findings.get("summary", {})

        # 五维度评分
        for dim in s.get("dimensions", []):
            did = dim.get("id", "?")
            label = _DIM_LABELS.get(did, did)
            score = dim.get("score", 0)
            passed = score >= _SCORE_THRESHOLD
            checks.append({
                "name": f"流程:{label}",
                "pass": passed,
                "status": status_from_bool(passed),
                "detail": f"{score}/100 | {dim.get('summary', '')}",
            })

        # 漏洞清单统计
        items = findings.get("findings", [])
        by_sev = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for f in items:
            sev = f.get("severity", "Low")
            by_sev[sev] = by_sev.get(sev, 0) + 1

        crit_high = by_sev.get("Critical", 0) + by_sev.get("High", 0)
        passed = crit_high == 0
        sev_parts = [f"{k}:{v}" for k, v in by_sev.items() if v > 0]
        checks.append({
            "name": "流程漏洞",
            "pass": passed,
            "status": status_from_bool(passed),
            "detail": f"{len(items)} 个漏洞 ({', '.join(sev_parts)})",
        })

        # 生成时间
        gen_at = findings.get("generated_at", "")
        if gen_at:
            checks.append({
                "name": "诊断时间",
                "pass": True,
                "status": "passed",
                "detail": f"Better Harness 报告生成于 {gen_at}",
            })

    def _report_evidence(self, checks: list[dict], evidence: dict):
        """解析 CLI 静态证据 → Loop 检查项。F5: 所有项带 status。
        
        Loop heuristic 自身不写入 .qoder/better-harness/，仅消费 CLI stdout 数据。
        """
        ev = evidence.get("evidence", {})

        # 项目信息
        proj = ev.get("project", {})
        if proj.get("available"):
            checks.append({
                "name": "项目概况",
                "pass": True,
                "status": "passed",
                "detail": f"{proj.get('name', '?')} | {proj.get('language', '?')} | "
                          f"{proj.get('sourceFiles', 0)} 源文件, {proj.get('testFiles', 0)} 测试文件 | "
                          f"Agent 指令: {proj.get('agentInstructions', {}).get('status', '?')}",
            })

        # 依赖健康
        deps = ev.get("dependencies", {})
        if deps.get("available"):
            risk = deps.get("riskLevel", "unknown")
            passed = risk in ("none", "low")
            checks.append({
                "name": "依赖健康度",
                "pass": passed,
                "status": status_from_bool(passed),
                "detail": f"风险等级: {risk} | 生态: {deps.get('ecosystems', [])}",
            })

        # 工作区漂移
        wt = ev.get("worktree", {})
        if wt.get("available"):
            changed = wt.get("changedFiles", 0)
            passed = changed == 0
            checks.append({
                "name": "工作区清洁度",
                "pass": passed,
                "status": status_from_bool(passed),
                "detail": f"未提交变更: {changed} 个文件",
            })

        # 会话可用性
        sess = ev.get("sessions", {})
        if sess.get("available"):
            checks.append({
                "name": "会话记录",
                "pass": True,
                "status": "passed",
                "detail": f"可用会话: {sess.get('usableSessionCount', 0)} | 模式: {sess.get('modelId', '?')}",
            })
