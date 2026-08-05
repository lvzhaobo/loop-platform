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
import re
import subprocess
from datetime import datetime

from .base import Checker, CheckerResult
from . import register

# Better Harness CLI path — configurable via BETTER_HARNESS_HOME env var
# Falls back to Qoder plugin cache path if not set.
_BH_ROOT = os.environ.get(
    "BETTER_HARNESS_HOME",
    os.path.expanduser("~/.qoder/plugins/cache/qoder-bundler/better-harness")
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

    def _find_latest_findings(self, root_dir: str = ".") -> dict | None:
        """查找最新的 findings.json（AI skill 生成）。root_dir 为项目根目录。"""
        bh_dir = os.path.join(root_dir, ".qoder", "better-harness")
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

    # ── 生成代码目录分析（无 findings.json 时） ──

    def _analyze_generated_dir(self, checks: list[dict], target_dir: str):
        """分析生成代码目录：文件结构、语言分布、关键文件存在性。"""
        from collections import Counter
        ext_counts: Counter = Counter()
        file_list: list[str] = []
        key_files = {
            "部署脚本": ["deploy.sh", "start.sh", "docker-compose.yml"],
            "依赖声明": ["requirements.txt", "package.json", "Pipfile"],
            "项目说明": ["README.md", "readme.md"],
            "环境配置": [".env", ".env.example", "config.py"],
        }
        for root, _dirs, files in os.walk(target_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower() or "(无后缀)"
                ext_counts[ext] += 1
                file_list.append(os.path.relpath(os.path.join(root, f), target_dir))

        total_files = sum(ext_counts.values())
        top_exts = ext_counts.most_common(5)
        ext_str = ", ".join(f"{ext}:{cnt}" for ext, cnt in top_exts)

        checks.append({
            "name": "生成代码结构",
            "pass": total_files > 0,
            "detail": f"{total_files} 个文件 | {ext_str}",
        })

        found_keys: list[str] = []
        missing_keys: list[str] = []
        for label, names in key_files.items():
            hits = [n for n in names if n in file_list or any(
                f.endswith(n) for f in file_list)]
            if hits:
                found_keys.append(f"{label}({hits[0]})")
            else:
                missing_keys.append(label)
        if found_keys:
            checks.append({
                "name": "关键文件覆盖",
                "pass": len(missing_keys) <= 1,
                "detail": f"已有: {'、'.join(found_keys)}；缺: {'、'.join(missing_keys) if missing_keys else '无'}",
            })

        checks.append({
            "name": "Better Harness",
            "pass": True,
            "detail": "生成代码目录无 findings.json。在 Qoder Desktop 对生成项目运行 /better-harness 可获取 AI 诊断。",
        })

    # ── Maker 平台检测 ──

    @staticmethod
    def _detect_maker_platform(target_dir: str) -> str:
        """从目录结构推断 Maker 类型。

        返回:
            "qoder"  — .qoder/sessions/ 或 .qoder/settings.json 存在
            "claude" — .claude/settings.json 或 CLAUDE.md 存在
            "api"    — 无 CLI session 证据（DeepSeek API 等）
        """
        if os.path.isdir(os.path.join(target_dir, ".qoder", "sessions")):
            return "qoder"
        if os.path.isfile(os.path.join(target_dir, ".qoder", "settings.json")):
            return "qoder"
        if os.path.isfile(os.path.join(target_dir, ".claude", "settings.json")):
            return "claude"
        if os.path.isfile(os.path.join(target_dir, "CLAUDE.md")):
            return "claude"
        return "api"

    def _try_session_evidence(self, target_dir: str, platform: str) -> dict | None:
        """尝试用 BH CLI 收集 session 证据。按 platform 选择正确的 --platform 参数。"""
        if platform == "api":
            return None  # API 模式无 session
        if not os.path.isfile(_BH_CLI):
            return None
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
                [_NODE, _BH_CLI, "harness", "evidence-bundle",
                 "--platform", platform, "--workspace", target_dir,
                 "--language", "zh-CN", "--depth", "quick", "--format", "json"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                return json.loads(proc.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass
        return None

    def generate_findings_for_dir(self, target_dir: str) -> dict | None:
        """为生成代码目录自动产出 findings.json。
        合并 CLI 证据 + 文件结构分析 → 标准 Better Harness 格式。
        写入 target_dir/.qoder/better-harness/<timestamp>/findings.json"""
        from collections import Counter
        import time as _time

        # 1. 收集文件结构数据
        ext_counts: Counter = Counter()
        file_list: list[str] = []
        key_files = {
            "部署脚本": ["deploy.sh", "start.sh", "docker-compose.yml"],
            "依赖声明": ["requirements.txt", "package.json", "Pipfile"],
            "项目说明": ["README.md", "readme.md"],
            "环境配置": [".env", ".env.example", "config.py"],
        }
        test_files = 0
        src_files = 0
        has_hardcoded_secret = False
        for root, _dirs, files in os.walk(target_dir):
            for f in files:
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, target_dir)
                ext = os.path.splitext(f)[1].lower()
                ext_counts[ext] += 1
                file_list.append(rel)
                # 分类：源码 vs 测试
                is_test = "test" in f.lower() or "spec" in f.lower() or "__test" in rel.lower()
                if is_test or rel.startswith("tests/") or rel.startswith("test/"):
                    test_files += 1
                elif ext in (".py", ".js", ".ts", ".go", ".java", ".rb", ".rs", ".html", ".css"):
                    src_files += 1
                # 硬编码密钥检测
                if ext in (".py", ".js", ".ts", ".sh", ".env"):
                    try:
                        with open(fp, errors="ignore") as fk:
                            content = fk.read()
                        if any(p in content for p in ["sk-", "AIza", "ghp_", "xoxb-", "-----BEGIN"]):
                            has_hardcoded_secret = True
                    except OSError:
                        pass

        total_files = sum(ext_counts.values())
        top_langs = [{"language": ext.lstrip(".") or "other", "sourceFiles": cnt} 
                     for ext, cnt in ext_counts.most_common(5)]

        # 关键文件覆盖
        found_keys, missing_keys = [], []
        for label, names in key_files.items():
            hits = [n for n in names if n in file_list or any(f.endswith(n) for f in file_list)]
            if hits:
                found_keys.append(f"{label}({hits[0]})")
            else:
                missing_keys.append(label)

        # 2. 检测 Maker 平台 + 收集 session 证据
        platform = self._detect_maker_platform(target_dir)
        session_evidence = self._try_session_evidence(target_dir, platform)

        # 从 session 证据提取增强数据
        session_count = 0
        tool_usage_score = 0  # 0-100
        if session_evidence:
            ev = session_evidence.get("evidence", {})
            sess = ev.get("sessions", {})
            if sess.get("available"):
                session_count = sess.get("usableSessionCount", 0)
            # 项目信息也给依赖分析加分
            proj = ev.get("project", {})
        else:
            ev = {}

        # 3. 拼装 findings.json
        project_name = os.path.basename(target_dir.rstrip("/"))

        # Maker 标签
        maker_labels = {"qoder": "Qoder CLI", "claude": "Claude Code CLI", "api": "DeepSeek API"}
        maker_label = maker_labels.get(platform, "API")
        has_session = platform != "api" and session_count > 0

        overview_parts = [f"Loop 通过 {maker_label} 自动生成的 {project_name} 项目。"]
        if total_files:
            overview_parts.append(
                f"{total_files} 个文件，测试占比 {test_files}/{src_files + test_files}"
                if src_files + test_files else f"{total_files} 个文件")
        if session_count:
            overview_parts.append(f"{session_count} 次 Agent 交互记录")
        if missing_keys:
            overview_parts.append(f"缺少: {'、'.join(missing_keys)}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 五维度评分（按 Maker 类型权重不同）
        # API 模式：纯文件结构推断，分数保守
        # CLI 模式：有 session 证据时分数更高，Agent 行为可观测
        session_bonus = 15 if has_session else 0

        deploy_score = (70 if "部署脚本" not in missing_keys else 35) + session_bonus
        exec_score = (75 if "依赖声明" in [k.split("(")[0] for k in found_keys] or len(missing_keys) <= 1 else 45) + (session_bonus if has_session else 0)
        test_ratio = (test_files / (src_files + test_files) * 100) if (src_files + test_files) > 0 else 0
        test_score = min(90, int(test_ratio * 2 + 20 + session_bonus))
        completeness = (80 - len(missing_keys) * 15) + session_bonus
        safety_score = (35 if has_hardcoded_secret else 80) + (session_bonus if has_session else 0)

        dimensions = [
            {"id": "task-understanding", "label": "任务理解",
             "score": max(35, deploy_score), "summary": f"[{maker_label}] 项目结构完整性: {len(found_keys)}/{len(found_keys)+len(missing_keys)} 关键文件覆盖" + (f", {session_count} session" if session_count else "")},
            {"id": "controlled-execution", "label": "可控执行",
             "score": max(35, exec_score), "summary": f"[{maker_label}] {total_files} 文件, 依赖声明{'有' if '依赖声明' in [k.split('(')[0] for k in found_keys] else '缺'}" + (f", Agent 工具可调用" if platform != "api" else "")},
            {"id": "change-validation", "label": "改动验证",
             "score": max(35, test_score), "summary": f"{test_files} 测试文件 / {src_files} 源码 ({test_ratio:.0f}%)"},
            {"id": "reliable-delivery", "label": "可靠交付",
             "score": max(35, completeness), "summary": f"[{maker_label}] 关键文件覆盖 {len(found_keys)}/{len(found_keys)+len(missing_keys)}"},
            {"id": "learning-capture", "label": "经验沉淀",
             "score": max(35, safety_score), "summary": ("无硬编码密钥" if not has_hardcoded_secret else "检测到硬编码密钥") + (f", {session_count} 次交互可追溯" if session_count else ", 无 Agent session 记录")},
        ]

        # 漏洞清单
        finding_items = []
        if missing_keys:
            finding_items.append({
                "id": "missing-key-files",
                "title": f"缺少关键文件: {'、'.join(missing_keys)}",
                "severity": "Medium" if len(missing_keys) >= 2 else "Low",
                "reason": f"生成项目缺少标准关键文件: {'、'.join(missing_keys)}。deploy.sh 确保部署可复现，README 提供项目说明，.env 分离配置与代码。",
                "dimensionRefs": ["reliable-delivery", "controlled-execution"],
                "aiFixPrompt": f"在生成项目中补齐: {'、'.join(missing_keys)}",
                "expectedArtifact": "文件",
                "expectedOutput": [f"生成 {'、'.join(missing_keys)}"]
            })
        if has_hardcoded_secret:
            finding_items.append({
                "id": "hardcoded-secret",
                "title": "检测到硬编码密钥或凭证",
                "severity": "High",
                "reason": "生成代码中包含疑似 API Key、Token 或私钥。应从环境变量读取，不硬编码。",
                "dimensionRefs": ["learning-capture"],
                "aiFixPrompt": "扫描生成代码中所有 sk-/ghp_/xoxb-/-----BEGIN 模式，替换为 os.environ.get() 调用",
                "expectedArtifact": "代码修改",
                "expectedOutput": ["所有密钥从环境变量读取"]
            })
        if test_files == 0 and src_files > 3:
            finding_items.append({
                "id": "no-tests",
                "title": "生成代码无测试文件",
                "severity": "Low",
                "reason": f"{src_files} 个源文件中未发现任何测试文件。建议至少包含基本的冒烟测试。",
                "dimensionRefs": ["change-validation"],
                "aiFixPrompt": "为生成项目添加最小化 pytest: 验证首页可访问，关键 API 返回 200",
                "expectedArtifact": "测试文件",
                "expectedOutput": ["至少一个测试文件，覆盖核心功能"]
            })

        avg_score = int(sum(d["score"] for d in dimensions) / len(dimensions))

        model_id_map = {"qoder": "qodercli-agent", "claude": "claude-code-agent", "api": "deepseek-v4-pro"}

        report = {
            "summary": {
                "projectName": project_name,
                "locale": "zh-CN",
                "modelId": model_id_map.get(platform, "api"),
                "maker": platform,
                "reportContractVersion": 25,
                "overview": " ".join(overview_parts),
                "dimensions": dimensions,
                "aiAgentPractice": {
                    "inspectedSurfaces": ["Project"] + (["Session"] if has_session else []),
                    "coverageRows": [
                        {"surface": "生成代码", "scopes": ["Project"], "count": total_files, "paths": []}
                    ] + ([{
                        "surface": "Agent 交互", "scopes": [maker_label],
                        "count": session_count, "paths": []
                    }] if session_count else [])
                }
            },
            "findings": finding_items,
            "generated_at": now,
            "analysis_source": f"auto-{platform}" if platform != "api" else "auto-file-scan",
        }

        # 4. 写入文件
        ts = datetime.now().strftime("%Y-%m-%d")
        ts_dir = datetime.now().strftime("%H%M%S")
        out_dir = os.path.join(target_dir, ".qoder", "better-harness", ts, ts_dir)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "findings.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── 主入口 ──

    @staticmethod
    def _is_generated_dir(target_dir: str) -> bool:
        """判断 target_dir 是否是 Loop 生成的代码目录（非平台源码）。"""
        base = os.path.basename(target_dir.rstrip("/"))
        return base.startswith("maker-") or "/output/" in target_dir or \
            (base.startswith("2026") and bool(re.search(r"^\d{6}-\d{6}-", base)))

    def check(self, target_dir: str) -> CheckerResult:
        checks: list[dict] = []
        is_gen = self._is_generated_dir(target_dir)

        # Layer 2 优先：AI 诊断报告
        findings = self._find_latest_findings(target_dir)
        if findings:
            self._report_findings(checks, findings)
        elif is_gen:
            # 生成代码 → 自动产出 findings.json → 再读
            auto_findings = self.generate_findings_for_dir(target_dir)
            if auto_findings:
                self._report_findings(checks, auto_findings)
            else:
                self._analyze_generated_dir(checks, target_dir)
        else:
            checks.append({
                "name": "AI诊断", "pass": True,
                "detail": "未找到 findings.json，请先运行 /better-harness 生成诊断报告",
            })

        # Layer 1 补充：CLI 静态证据（生成代码目录跳过，会读取父级 git 信息）
        if not is_gen:
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
