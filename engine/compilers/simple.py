"""SimpleCompiler — 将自由文本需求转为 fixture-backend 式 Spec 三件套。

Phase 2: 包装现有 spec_compiler.py CLI 调用（确定性离线路径 + LLM 路径）。
默认工作在 workspace 的 cases/<task>/ 下。
"""

from __future__ import annotations

import json
import os
import subprocess

from engine.core.contracts import RunContext, SpecBundle
from engine.compilers.base import Compiler, CompilerError
from engine.compilers.registry import register
from engine.core.paths import PlatformPaths


@register("simple")
class SimpleCompiler(Compiler):
    """基于现有 spec_compiler.py 的轻量编译器。

    两种模式:
    - 离线 (HARNESS_MODE=sample): 用 mock 内置 recipe 生成 fixture 三件套
    - 真实 LLM: 调用 DeepSeek 编译自然语言需求
    """

    name = "simple"

    def compile(self, context: RunContext, requirement: str) -> SpecBundle:
        workspace = context.workspace
        task = context.task

        case_dir = os.path.join(workspace, "cases", task)
        spec_dir = os.path.join(case_dir, "spec")
        manifest_path = os.path.join(spec_dir, "manifest.json")
        acceptance_path = os.path.join(spec_dir, "acceptance.json")
        spec_path = os.path.join(case_dir, "requirement.md")
        if not os.path.isfile(spec_path):
            # 历史 case 将主 Spec 放在 spec/spec.md；兼容读取但不复制或双写。
            spec_path = os.path.join(spec_dir, "spec.md")

        # 如果 case 目录已存在且三件套齐全 → 直接复用（幂等）
        if (os.path.isfile(spec_path) and os.path.isfile(manifest_path)
                and os.path.isfile(acceptance_path)):
            return SpecBundle(
                spec_path=spec_path,
                manifest_path=manifest_path,
                acceptance_path=acceptance_path,
                provenance="simple",
                meta={"source": "existing"},
            )

        # 尝试调用 spec_compiler.py CLI
        cli_path = str(PlatformPaths.ENGINE_DIR / "tools" / "spec_compiler.py")
        if not os.path.isfile(cli_path):
            raise CompilerError(f"spec_compiler.py 未找到: {cli_path}")

        is_sample = os.environ.get("HARNESS_MODE") == "sample"

        try:
            cmd = [
                "python3", cli_path,
                "--name", task,
                "--archetype", "spec",
            ]
            if is_sample:
                cmd.append("--mock")
            elif requirement.strip():
                # 将需求文本写入临时文件
                req_file = os.path.join(workspace, "data", f"_req_{task}.txt")
                os.makedirs(os.path.dirname(req_file), exist_ok=True)
                with open(req_file, "w") as f:
                    f.write(requirement)
                cmd.extend(["--input", req_file])
            else:
                # 尝试从已有文件读取
                if os.path.isfile(spec_path):
                    with open(spec_path) as f:
                        content = f.read()
                    if content.strip():
                        cmd.extend(["--text", content.strip()])

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=workspace,
            )

            if proc.returncode != 0:
                raise CompilerError(
                    f"spec_compiler 失败 (exit {proc.returncode}): {proc.stderr[:200]}"
                )

            # 验证产出，并兼容 CLI 将主 Spec 写入 spec/spec.md 的既有布局。
            if not os.path.isfile(spec_path):
                legacy_spec_path = os.path.join(spec_dir, "spec.md")
                if os.path.isfile(legacy_spec_path):
                    spec_path = legacy_spec_path
            if not os.path.isfile(spec_path):
                raise CompilerError(f"主 Spec 未生成: {spec_path}")
            if not os.path.isfile(manifest_path):
                raise CompilerError(f"manifest.json 未生成: {manifest_path}")
            if not os.path.isfile(acceptance_path):
                raise CompilerError(f"acceptance.json 未生成: {acceptance_path}")

            return SpecBundle(
                spec_path=spec_path,
                manifest_path=manifest_path,
                acceptance_path=acceptance_path,
                provenance="simple",
                meta={"source": "cli", "mock": is_sample},
            )

        except subprocess.TimeoutExpired:
            raise CompilerError("spec_compiler 超时 (120s)")
