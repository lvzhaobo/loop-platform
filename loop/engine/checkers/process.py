"""流程质量 Checker。调用 Better Harness CLI 收集静态证据，读取 AI 生成的 findings.json。

两层架构:
    Layer 1 - 静态证据（always available）: 项目规模、依赖健康度、工作区漂移、会话可用性
    Layer 2 - AI 诊断（需先运行 /better-harness skill）: 五维度评分 + 优先级漏洞清单

用法:
    from checkers.process import ProcessChecker
    checker = ProcessChecker()
    result = checker.check(target_dir="output/maker-xxx")
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from .base import Checker, CheckerResult
from . import register

# Better Harness CLI 路径（Qoder 插件缓存）
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


@register("process")
class ProcessChecker(Checker):
    """Better Harness 流程质量评估器。"""

    name = "process"

    # ── Layer 1: 静态证据（CLI，无 AI 依赖） ──

    def _run_cli_evidence(self, target_dir: str) -> dict | None:
        """运行 better-harness report --json，返回静态证据。CLI 不可用时返回 None。"""
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

    def _find_latest_findings(self) -> dict | None:
        """查找最新的 findings.json（AI skill 生成）。"""
        bh_dir = os.path.join(".qoder", "better-harness")
        if not os.path.isdir(bh_dir):
            return None
        # 按日期/时间倒序遍历
        best = None
        best_ts = ""
        for date_dir in sorted(os.listdir(bh_dir), reverse=True):
            dp = os.path.join(bh_dir, date_dir)
            if not os.path.isdir(dp):
                continue
            for ts_dir in sorted(os.listdir(dp), reverse=True):
                fp = os.path.join(dp, ts_dir, "findings.json")
                if os.path.isfile(fp):
                    if ts_dir > best_ts:
                        best_ts = ts_dir
                        best = fp
        if best:
            try:
                with open(best, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return None

    # ── 主入口 ──

    def check(self, target_dir: str) -> CheckerResult:
        checks: list[dict] = []

        # Layer 2 优先：AI 诊断报告
        findings = self._find_latest_findings()
        if findings:
            self._report_findings(checks, findings)
        else:
            checks.append({
                "name": "AI诊断", "pass": True,
                "detail": "未找到 findings.json，请先运行 /better-harness 生成诊断报告",
            })

        # Layer 1 补充：CLI 静态证据
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
        """解析 AI 生成的 findings.json → Loop 检查项。"""
        s = findings.get("summary", {})

        # 五维度评分
        for dim in s.get("dimensions", []):
            did = dim.get("id", "?")
            label = _DIM_LABELS.get(did, did)
            score = dim.get("score", 0)
            checks.append({
                "name": f"流程:{label}",
                "pass": score >= 60,
                "detail": f"{score}/100 | {dim.get('summary', '')}",
            })

        # 漏洞清单统计
        items = findings.get("findings", [])
        by_sev = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for f in items:
            sev = f.get("severity", "Low")
            by_sev[sev] = by_sev.get(sev, 0) + 1

        sev_parts = [f"{k}:{v}" for k, v in by_sev.items() if v > 0]
        checks.append({
            "name": "流程漏洞",
            "pass": by_sev.get("Critical", 0) + by_sev.get("High", 0) == 0,
            "detail": f"{len(items)} 个漏洞 ({', '.join(sev_parts)})",
        })

        # 生成时间
        gen_at = findings.get("generated_at", "")
        if gen_at:
            checks.append({
                "name": "诊断时间",
                "pass": True,
                "detail": f"Better Harness 报告生成于 {gen_at}",
            })

    def _report_evidence(self, checks: list[dict], evidence: dict):
        """解析 CLI 静态证据 → Loop 检查项。"""
        ev = evidence.get("evidence", {})

        # 项目信息
        proj = ev.get("project", {})
        if proj.get("available"):
            checks.append({
                "name": "项目概况",
                "pass": True,
                "detail": f"{proj.get('name', '?')} | {proj.get('language', '?')} | "
                          f"{proj.get('sourceFiles', 0)} 源文件, {proj.get('testFiles', 0)} 测试文件 | "
                          f"Agent 指令: {proj.get('agentInstructions', {}).get('status', '?')}",
            })

        # 依赖健康
        deps = ev.get("dependencies", {})
        if deps.get("available"):
            risk = deps.get("riskLevel", "unknown")
            checks.append({
                "name": "依赖健康度",
                "pass": risk in ("none", "low"),
                "detail": f"风险等级: {risk} | 生态: {deps.get('ecosystems', [])}",
            })

        # 工作区漂移
        wt = ev.get("worktree", {})
        if wt.get("available"):
            changed = wt.get("changedFiles", 0)
            checks.append({
                "name": "工作区清洁度",
                "pass": changed == 0,
                "detail": f"未提交变更: {changed} 个文件",
            })

        # 会话可用性
        sess = ev.get("sessions", {})
        if sess.get("available"):
            checks.append({
                "name": "会话记录",
                "pass": True,
                "detail": f"可用会话: {sess.get('usableSessionCount', 0)} | 模式: {sess.get('modelId', '?')}",
            })
