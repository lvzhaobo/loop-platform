"""Phase 2 兼容收口 — 将现有 Maker/Checker 包装为 Phase 2 合同。

不修改既有 provider，仅添加 RunContext/SpecBundle/ArtifactBundle 适配层。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from engine.core.contracts import RunContext, SpecBundle, ArtifactBundle, CheckReport
from engine.core.paths import PlatformPaths


# ── Maker 兼容 ──

def make_with_context(
    context: RunContext,
    spec: SpecBundle,
    maker_name: str = "deepseek_api",
    feedback: str | None = None,
    requirement: str = "",
    timeout_seconds: int | None = None,
    cost_limit_yuan: float | None = None,
) -> ArtifactBundle:
    """用 Phase 2 合同调用既有 Maker。

    Args:
        context: 运行上下文
        spec: Spec 三件套
        maker_name: Maker 名称（默认 deepseek_api）
        feedback: 上一轮验证失败反馈

    Returns:
        ArtifactBundle: 制品包
    """
    from engine.makers import load_maker

    maker_config = {}
    # SampleMaker 是零配置的确定性本地实现；Profile 的通用超时预算
    # 仍用于受支持的 Provider，不能作为构造参数传给 SampleMaker。
    if timeout_seconds is not None and maker_name != "sample":
        maker_config["timeout_seconds"] = timeout_seconds
    maker = load_maker(maker_name, **maker_config)
    # 使用完整 run_id 隔离每次制品，禁止按日期前缀复用历史输出。
    output_dir = os.path.join(PlatformPaths.OUTPUT_DIR, f"maker-{context.run_id}")

    # 构建 enhanced prompt（含 spec 内容）
    prompt_parts = []
    for path in [spec.spec_path, spec.manifest_path, spec.acceptance_path]:
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            tag = os.path.basename(path).replace(".json", "").replace(".md", "")
            prompt_parts.append(f"# {tag}\n{content}")
    if not prompt_parts:
        from engine.tools.compile_spec import derive
        # 尝试从 manifest 派生 prompt
        if os.path.isfile(spec.manifest_path):
            prompt_parts.append(f"# spec\n{open(spec.manifest_path).read()}")

    prompt = "\n\n".join(prompt_parts)
    if requirement.strip():
        prompt = f"# original_requirement\n{requirement.strip()}\n\n{prompt}"
    try:
        acceptance = json.loads(Path(spec.acceptance_path).read_text(encoding="utf-8"))
        pages = acceptance.get("pages") if acceptance.get("schema_version") == 2 else None
        if isinstance(pages, list):
            files = [page.get("file") for page in pages if isinstance(page, dict)]
            prompt += ("\n\n# artifact_page_contract\n必须创建且只使用 acceptance 中声明的页面文件："
                       + ", ".join(str(item) for item in files)
                       + "。每个 declared navigation 必须以对应 <a href> 实现；不得链接未生成的本地文件。")
    except (OSError, ValueError, TypeError):
        pass

    result = maker.generate(str(output_dir), prompt, feedback=feedback)
    if not result.success:
        raise RuntimeError(f"Maker {maker_name} 失败: {result.error or '未返回制品'}")
    if cost_limit_yuan is not None and result.cost_estimate_yuan > cost_limit_yuan:
        raise RuntimeError(f"Maker 估算成本 {result.cost_estimate_yuan} 超过上限 {cost_limit_yuan}")
    if not result.files:
        raise RuntimeError(f"Maker {maker_name} 未返回业务文件")

    # 只把 Maker 显式声明的业务文件纳入 artifact；不吸收调试文本或未声明副产物。
    files = sorted(result.files)

    hasher = hashlib.sha256()
    root = os.path.realpath(output_dir)
    for fn in files:
        full_path = os.path.realpath(os.path.join(root, fn))
        if not full_path.startswith(root + os.sep) or not os.path.isfile(full_path):
            raise RuntimeError(f"Maker 返回的制品文件非法或缺失: {fn}")
        with open(full_path, "rb") as f:
            hasher.update(f.read())
    digest = hasher.hexdigest()

    return ArtifactBundle(
        output_dir=str(output_dir),
        files=files,
        digest=digest,
        meta={
            "model": result.model,
            "cost_estimate_yuan": result.cost_estimate_yuan,
            "maker": maker_name,
        },
    )


# ── Checker 兼容 ──

def check_with_context(
    context: RunContext,
    artifacts: ArtifactBundle,
    checker_names: list[str] | None = None,
    acceptance_path: str = "",
) -> CheckReport:
    """用 Phase 2 合同调用既有 Checker。

    Args:
        context: 运行上下文（含 run_id 用于 BH 绑定）
        artifacts: 制品包
        checker_names: Checker 名称列表（默认全部）

    Returns:
        CheckReport: 检查报告
    """
    from engine.checkers import load_checker, list_checkers

    names = checker_names or list_checkers()
    all_checks = []
    evidence = {}

    for name in names:
        try:
            checker = load_checker(name)
            result = checker.check(artifacts.output_dir, run_id=context.run_id, acceptance_path=acceptance_path)
            for c in result.checks:
                # 标记来源 checker
                if "checker" not in c:
                    c["checker"] = name
                all_checks.append(c)
            # 记录证据引用
            status_sum = result.summarize()
            evidence[name] = {
                "status_summary": status_sum,
                "total": result.total_count,
                "pass": result.pass_count,
            }
        except Exception as e:
            all_checks.append({
                "name": f"Checker:{name}",
                "pass": False,
                "status": "unavailable",
                "detail": str(e)[:200],
                "checker": name,
            })

    # 汇总状态
    from engine.checkers.base import CheckStatus
    has_failure = any(c.get("status") == "failed" or
                      (c.get("pass") is False and c.get("status") != "unavailable")
                      for c in all_checks)
    has_unavailable = any(c.get("status") == "unavailable" for c in all_checks)
    all_passed = all(c.get("pass") or c.get("status") == "skipped" for c in all_checks)

    if all_passed and not has_unavailable:
        status: CheckStatus = "passed"
    elif has_unavailable and not has_failure:
        status = "indeterminate"
    elif has_failure:
        status = "failed"
    else:
        status = "unavailable"

    return CheckReport(
        status=status,
        checks=all_checks,
        evidence=evidence,
        summary={
            "total": len(all_checks),
            "passed": sum(1 for c in all_checks if c.get("pass")),
            "checkers": names,
        },
    )
