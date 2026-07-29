"""delivery-loop 发布器:把 harness-4 生成的产物发布到 GitHub。

支持两种布局(由 HARNESS_GIT_SUBDIR 决定):
- 子目录模式(HARNESS_GIT_SUBDIR 非空,如 sample1):
    克隆目标仓库 → 把产物拷进 <subdir>/ → 提交 → 推到 HARNESS_GIT_BRANCH(默认 main)。
    适合「一个仓库收纳多个样例」。
- 分支模式(未设 HARNESS_GIT_SUBDIR):
    在产物目录内 git init → 建独立分支 → 提交 → 推送。每个样例一个分支。

无 token / 未配远端 / HARNESS_GIT_PUSH=0 时,自动降级为「仅本地提交」(在产物目录内),
便于零密钥自测。凭证从环境变量读(仓库根 .env):GITHUB_TOKEN。
推送/克隆用带 token 的一次性 URL,**不写入持久 .git/config、不打印明文**。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

# 拷贝产物到子目录时排除的噪音(与 harness-4 的验证元数据/缓存一致)
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "_run_meta.json",
                                 "_verify.log", "reports", ".git")


def _run(args: list[str], cwd: str) -> tuple[int, str]:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def _scrub(text: str, secret: str | None) -> str:
    return text.replace(secret, "****") if secret else text


# HTTP/2 framing layer 错误的稳定规避:git 网络命令强制走 HTTP/1.1(命令级,不改全局配置)
_HTTP1 = ["-c", "http.version=HTTP/1.1"]


def _next_subdir(repo: str, prefix: str) -> tuple[str, int]:
    """B 方案:扫描仓库顶层已存在的 <prefix><N> 目录,返回下一个可用目录名与序号(从 1 起)。"""
    pat = re.compile(r"^" + re.escape(prefix) + r"(\d+)$")
    nums: list[int] = []
    try:
        for name in os.listdir(repo):
            m = pat.match(name)
            if m and os.path.isdir(os.path.join(repo, name)):
                nums.append(int(m.group(1)))
    except OSError:
        pass
    n = (max(nums) + 1) if nums else 1
    return f"{prefix}{n}", n


def _write_gitignore(path: str) -> None:
    ignore = os.path.join(path, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as f:
            f.write("__pycache__/\n*.pyc\n_run_meta.json\n_verify.log\nreports/\n")


def _local_commit(out_dir: str, branch: str, message: str,
                  author: str, email: str, reason: str) -> dict:
    """零密钥自测:在产物目录内本地提交(不推送)。"""
    result: dict = {"committed": False, "pushed": False, "branch": branch}
    _write_gitignore(out_dir)
    for args in (
        ["git", "init", "-q"],
        ["git", "checkout", "-q", "-B", branch],
        ["git", "add", "-A"],
        ["git", "-c", f"user.name={author}", "-c", f"user.email={email}",
         "commit", "-q", "-m", message],
    ):
        code, out = _run(args, out_dir)
        if code != 0:
            result["reason"] = f"本地提交失败({args[1]}):{out}"
            return result
    code, sha = _run(["git", "rev-parse", "--short", "HEAD"], out_dir)
    result["committed"] = True
    result["commit"] = sha if code == 0 else "unknown"
    result["reason"] = reason
    return result


def _publish_subdir(out_dir: str, subdir: str, branch: str, message: str,
                    remote: str, token: str, author: str, email: str,
                    auto: bool = False, prefix: str = "sample",
                    port_base: int = 1000) -> dict:
    """子目录模式:克隆目标仓 → 覆盖写 <subdir>/ → 提交 → 推送到 branch。

    auto=True(B 方案):克隆后自动递增取下一个 <prefix><N>,不覆盖旧样例;
    并回填 sample_n 与 port(=port_base+N)供部署层使用。
    """
    result: dict = {"committed": False, "pushed": False, "branch": branch}
    url = f"https://x-access-token:{token}@{remote}"
    work = tempfile.mkdtemp(prefix="loop-publish-")
    try:
        # 克隆已有仓库;空仓库/新仓库克隆后无分支,后续 checkout -B 补齐
        code, out = _run(["git", *_HTTP1, "clone", "-q", url, "repo"], work)
        repo = os.path.join(work, "repo")
        if code != 0:
            result["reason"] = "克隆目标仓失败:" + _scrub(out, token)
            return result
        _run(["git", "checkout", "-q", "-B", branch], repo)
        # B 方案:克隆后根据仓库现状算出下一个 sampleN 与对应端口
        if auto:
            subdir, n = _next_subdir(repo, prefix)
            result["sample_n"] = n
            result["port"] = str(port_base + n)
        result["subdir"] = subdir
        # 覆盖写子目录(先清空旧内容,保证与本次产物一致;auto 模式下为全新目录)
        dest = os.path.join(repo, subdir)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(out_dir, dest, ignore=_IGNORE)
        _write_gitignore(dest)
        for args in (
            ["git", "add", "-A"],
            ["git", "-c", f"user.name={author}", "-c", f"user.email={email}",
             "commit", "-q", "-m", message],
        ):
            code, out = _run(args, repo)
            if code != 0:
                # 无改动时 commit 返回非 0:内容已在远端,视为已发布(幂等),仍可触发部署
                if "nothing to commit" in out:
                    result["committed"] = True
                    result["pushed"] = True
                    result["up_to_date"] = True
                    result["commit"] = "up-to-date"
                    result["remote"] = remote
                    result["path"] = f"{subdir}/ @ {branch}"
                    result["reason"] = "内容与远端一致,无需推送"
                    return result
                result["reason"] = f"提交失败({args[1]}):" + _scrub(out, token)
                return result
        code, sha = _run(["git", "rev-parse", "--short", "HEAD"], repo)
        result["committed"] = True
        result["commit"] = sha if code == 0 else "unknown"
        code, out = _run(["git", *_HTTP1, "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], repo)
        if code != 0:
            result["reason"] = "推送失败:" + _scrub(out, token)
            return result
        result["pushed"] = True
        result["remote"] = remote
        result["path"] = f"{subdir}/ @ {branch}"
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _publish_branch(out_dir: str, branch: str, message: str,
                    remote: str, token: str, author: str, email: str) -> dict:
    """分支模式:产物目录内 git init → 提交 → 推送到独立分支。"""
    result = _local_commit(out_dir, branch, message, author, email, reason="")
    if not result.get("committed"):
        return result
    url = f"https://x-access-token:{token}@{remote}"
    code, out = _run(["git", *_HTTP1, "push", "-q", url, f"HEAD:refs/heads/{branch}"], out_dir)
    if code != 0:
        result["reason"] = "推送失败:" + _scrub(out, token)
        return result
    result["pushed"] = True
    result["remote"] = remote
    result.pop("reason", None)
    return result


def publish(out_dir: str, branch: str, message: str) -> dict:
    """提交产物并按配置推送到 GitHub。返回结果字典。

    branch 仅在分支模式下作为分支名;子目录模式使用 HARNESS_GIT_BRANCH(默认 main)。
    """
    remote = os.environ.get("HARNESS_GIT_REMOTE", "").strip()  # github.com/owner/repo.git(不含 token)
    token = os.environ.get("GITHUB_TOKEN")
    do_push = os.environ.get("HARNESS_GIT_PUSH", "1") == "1"
    subdir = os.environ.get("HARNESS_GIT_SUBDIR", "").strip()
    author = os.environ.get("HARNESS_GIT_AUTHOR", "harness-bot")
    email = os.environ.get("HARNESS_GIT_EMAIL", "harness-bot@users.noreply.github.com")
    # B 方案:自动递增子目录
    auto = os.environ.get("HARNESS_GIT_SUBDIR_AUTO", "0") == "1"
    prefix = os.environ.get("HARNESS_GIT_SUBDIR_PREFIX", "sample").strip() or "sample"
    try:
        port_base = int(os.environ.get("HARNESS_PORT_BASE", "1000"))
    except ValueError:
        port_base = 1000

    can_push = do_push and remote and token
    if not can_push:
        reason = ("HARNESS_GIT_PUSH=0,仅本地提交(未推送)" if not do_push
                  else "未配置 HARNESS_GIT_REMOTE 或 GITHUB_TOKEN,跳过推送")
        return _local_commit(out_dir, branch, message, author, email, reason)

    if subdir or auto:
        target_branch = os.environ.get("HARNESS_GIT_BRANCH", "main").strip() or "main"
        assert token  # can_push 已保证非空,收窄类型
        return _publish_subdir(out_dir, subdir, target_branch, message,
                               remote, token, author, email,
                               auto=auto, prefix=prefix, port_base=port_base)
    assert token  # can_push 已保证非空,收窄类型
    return _publish_branch(out_dir, branch, message, remote, token, author, email)
