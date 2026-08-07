"""受控 GitHub Delivery：固定目标仓库、递增 sampleN，并由仓库 Workflow 接管部署。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from engine.core.contracts import ArtifactBundle, DeliveryResult, RunContext
from engine.core.paths import PlatformPaths, load_config
from pipeline.delivery.base import Delivery
from pipeline.delivery.registry import register

_REPO = "github.com/lvzhaobo/loop-sample.git"
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")
_SAFE_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


def _inside_output(path: str) -> Path:
    resolved = Path(path).resolve()
    root = PlatformPaths.OUTPUT_DIR.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("只允许交付当前 output/ 下的制品")
    return resolved


@register("github_workflow")
class GitHubWorkflowDelivery(Delivery):
    """推送不可变制品到固定仓库；不执行 SSH/ECS 命令。"""

    name = "github_workflow"

    def __init__(self, *, repo: str = _REPO, branch: str = "main", prefix: str = "sample",
                 port_base: int = 1000, workflow_deploy: bool = True):
        if repo != _REPO:
            raise ValueError("GitHub Delivery 仅允许目标仓库 github.com/lvzhaobo/loop-sample.git")
        if not _SAFE_BRANCH.fullmatch(branch) or branch.startswith("-"):
            raise ValueError("GitHub 分支名非法")
        if not _SAFE_PREFIX.fullmatch(prefix):
            raise ValueError("sample 前缀非法")
        if isinstance(port_base, bool) or not isinstance(port_base, int) or not 1 <= port_base <= 65000:
            raise ValueError("port_base 必须是 1 到 65000 的整数")
        if workflow_deploy is not True:
            raise ValueError("GitHub Delivery 必须由仓库 Workflow 接管部署")
        self.repo, self.branch, self.prefix, self.port_base = repo, branch, prefix, port_base

    def plan(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        _inside_output(artifacts.output_dir)
        return DeliveryResult(
            status="plan_only",
            location=f"https://{self.repo.removesuffix('.git')}/tree/{self.branch}",
            plan={"adapter": self.name, "repo": self.repo, "branch": self.branch,
                  "prefix": self.prefix, "port_base": self.port_base,
                  "artifact_digest": artifacts.digest, "run_id": context.run_id,
                  "deployment": "repository-workflow"},
            meta={"adapter": self.name, "dry_run": True},
        )

    def deliver(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        source = _inside_output(artifacts.output_dir)
        token = load_config().get("GITHUB_TOKEN", "").strip()
        if not token:
            return DeliveryResult(status="failed", reason="GITHUB_TOKEN 未设置")
        if not shutil.which("git"):
            return DeliveryResult(status="failed", reason="未找到 git 命令")
        with tempfile.TemporaryDirectory(prefix="loop-github-delivery-") as work:
            askpass = Path(work) / "askpass.sh"
            askpass.write_text(
                "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' 'x-access-token' ;; *) printf '%s\\n' \"$LOOP_GITHUB_TOKEN\" ;; esac\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0",
                   "LOOP_GITHUB_TOKEN": token}
            repo_dir = Path(work) / "repo"
            try:
                self._git(["clone", "--quiet", "--depth", "1", "--single-branch", "--branch", self.branch,
                           f"https://x-access-token@{self.repo}", str(repo_dir)], work, env)
                self._git(["checkout", "--quiet", self.branch], str(repo_dir), env)
                sample_n = self._next_sample(repo_dir)
                subdir = f"{self.prefix}{sample_n}"
                destination = repo_dir / subdir
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
                port = self.port_base + sample_n
                if port > 65535:
                    raise RuntimeError("递增端口已超出 65535，拒绝发布")
                (destination / "loop-delivery.json").write_text(json.dumps({
                    "schema_version": 1, "run_id": context.run_id, "artifact_digest": artifacts.digest,
                    "sample": subdir, "port": port, "deployment": "repository-workflow",
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                self._git(["add", "--", subdir], str(repo_dir), env)
                self._git(["-c", "user.name=Loop Delivery", "-c", "user.email=loop-delivery@local",
                           "commit", "--quiet", "-m", f"loop: deliver {context.run_id}"], str(repo_dir), env)
                commit_sha = self._git(["rev-parse", "HEAD"], str(repo_dir), env).strip()
                self._git(["push", "--quiet", "origin", f"HEAD:refs/heads/{self.branch}"], str(repo_dir), env)
            except RuntimeError as exc:
                return DeliveryResult(status="failed", reason=str(exc)[:500])
        url = f"https://{self.repo.removesuffix('.git')}/tree/{self.branch}/{subdir}"
        return DeliveryResult(status="passed", location=url,
                              reason="GitHub 制品已推送；ECS Workflow 与公网健康尚未在本次 Delivery 中验证",
                              plan={
                                  "adapter": self.name, "repo": self.repo, "branch": self.branch, "sample": subdir,
                                  "port": port, "artifact_digest": artifacts.digest, "run_id": context.run_id,
                                  "commit_sha": commit_sha, "deployment": "github-published-awaiting-workflow",
                              }, meta={
                                  "adapter": self.name, "publish_status": "passed",
                                  "workflow_status": "pending", "ecs_health": "unverified",
                              })

    @staticmethod
    def _next_sample(repo_dir: Path) -> int:
        numbers = []
        for child in repo_dir.iterdir():
            match = re.fullmatch(r"sample(\d+)", child.name)
            if child.is_dir() and match:
                numbers.append(int(match.group(1)))
        return max(numbers, default=0) + 1

    @staticmethod
    def _git(args: list[str], cwd: str, env: dict[str, str]) -> str:
        completed = subprocess.run(["git", *args], cwd=cwd, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        if completed.returncode:
            output = completed.stdout.replace(env.get("LOOP_GITHUB_TOKEN", ""), "<redacted>")
            raise RuntimeError(f"GitHub 交付失败: {output[-400:]}")
        return completed.stdout
