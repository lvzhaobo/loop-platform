"""loop/pipeline 部署器:拉取式部署到阿里云 ECS。

策略(与用户约定):代码已发布到 GitHub,ECS 侧直接 git 拉取运行,不 scp 源码。
流程(SSH 进 ECS 执行远端脚本):
  clone/pull 目标仓库 → 进 <subdir>/ → pip 装依赖 → 杀旧进程 → nohup 起 app.py。

认证:SSH 密码。用 Python 标准库 pty 驱动系统 ssh 并在提示时喂密码,
**不依赖 sshpass/paramiko**(前者 macOS 难装,后者在 Python 3.14 上无预编译包)。
凭证从环境变量读(仓库根 .env):ECS_SSH_PASSWORD(必填)、GITHUB_TOKEN(私有仓库拉取时需要)。
所有输出中的 token/密码**不打印明文**(替换为 ****)。
"""
from __future__ import annotations

import base64
import os
import pty
import select
import shutil
import time


def _scrub(text: str, *secrets: str | None) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "****")
    return text


def _repo_name(remote: str) -> str:
    """从 github.com/owner/repo.git 取仓库名 repo。"""
    name = remote.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def _ssh_with_password(argv: list[str], password: str, timeout: int = 240) -> tuple[int, str]:
    """用 pty 运行 ssh,在出现 password 提示时喂一次密码;收集全部输出直到结束。"""
    pid, fd = os.forkpty()
    if pid == 0:  # 子进程:执行 ssh
        os.execvp(argv[0], argv)
        os._exit(127)  # execvp 失败兜底
    out = b""
    sent = False
    deadline = time.time() + timeout
    while True:
        if time.time() > deadline:
            break
        try:
            r, _, _ = select.select([fd], [], [], 1.0)
        except OSError:
            break
        if fd in r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break  # pty 关闭
            if not data:
                break
            out += data
            if not sent and b"assword" in out:  # 匹配 "password:" / "Password:"
                os.write(fd, password.encode() + b"\n")
                sent = True
    try:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        code = 0
    return code, out.decode("utf-8", "replace")


def deploy(app_port: str, subdir: str | None = None,
           retain: int | None = None, prefix: str | None = None) -> dict:
    """SSH 到 ECS 执行拉取式部署。返回结果字典。

    subdir/app_port:优先用参数(由 publisher 算出的 sampleN 与端口);未传时回退环境变量。
    retain(B 方案):部署后只保留最近 retain 个样例进程存活,其余停进程(目录仍留 git)。
    """
    host = os.environ.get("ECS_HOST", "").strip()
    user = os.environ.get("ECS_SSH_USER", "root").strip() or "root"
    ssh_port = os.environ.get("ECS_SSH_PORT", "22").strip() or "22"
    password = os.environ.get("ECS_SSH_PASSWORD")
    remote = os.environ.get("HARNESS_GIT_REMOTE", "").strip()
    branch = os.environ.get("HARNESS_GIT_BRANCH", "main").strip() or "main"
    subdir = (subdir if subdir is not None
              else os.environ.get("HARNESS_GIT_SUBDIR", "")).strip()
    token = os.environ.get("GITHUB_TOKEN")
    base = os.environ.get("ECS_REMOTE_DIR", "~/apps").strip() or "~/apps"
    prefix = prefix or os.environ.get("HARNESS_GIT_SUBDIR_PREFIX", "sample").strip() or "sample"
    if retain is None:
        try:
            retain = int(os.environ.get("ECS_RETAIN", "5"))
        except ValueError:
            retain = 5

    result: dict = {"deployed": False, "host": host}

    if not host or not password:
        result["reason"] = "未配置 ECS_HOST 或 ECS_SSH_PASSWORD,跳过部署"
        return result
    if not remote:
        result["reason"] = "未配置 HARNESS_GIT_REMOTE,无法拉取,跳过部署"
        return result
    if not shutil.which("ssh"):
        result["reason"] = "本机未找到 ssh 命令"
        return result

    repo = _repo_name(remote)
    clone_url = f"https://x-access-token:{token}@{remote}" if token else f"https://{remote}"
    workdir = f"{base}/{repo}/{subdir}" if subdir else f"{base}/{repo}"

    # 远端脚本:幂等拉取 + 重启。app.pid 按子目录隔离,避免误杀其它样例。
    # 启动优先级:产物自带 deploy.sh(由 Maker 随代码生成,契约:读 PORT 环境变量、
    # 后台起服务并写 app.pid/app.log) → 回退旧契约(requirements.txt + app.py)。
    remote_script = f"""set -e
mkdir -p {base}
cd {base}
if [ -d {repo}/.git ]; then
  cd {repo}
  git -c http.version=HTTP/1.1 remote set-url origin '{clone_url}'
  git -c http.version=HTTP/1.1 fetch -q origin {branch}
  git -c http.version=HTTP/1.1 reset -q --hard origin/{branch}
else
  git -c http.version=HTTP/1.1 clone -q -b {branch} '{clone_url}' {repo}
  cd {repo}
fi
cd {workdir}
if [ -f app.pid ]; then kill "$(cat app.pid)" 2>/dev/null || true; sleep 1; rm -f app.pid; fi
if [ -f deploy.sh ]; then
  PORT={app_port} bash deploy.sh > deploy.log 2>&1
else
  [ -f requirements.txt ] && (python3 -m pip install -q -r requirements.txt || pip3 install -q -r requirements.txt) || true
  PORT={app_port} setsid nohup python3 app.py > app.log 2>&1 &
  echo $! > app.pid
fi
sleep 2
if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then echo "DEPLOY_OK pid=$(cat app.pid) port={app_port}"; else echo "DEPLOY_FAIL"; tail -n 20 deploy.log app.log 2>/dev/null; exit 1; fi
# B 方案清理:只保留最近 {retain} 个样例进程存活,其余停进程(目录仍留 git,不删)
cd {base}/{repo}
for D in $(ls -d {prefix}*/ 2>/dev/null | sed 's#/##' | grep -E '^{prefix}[0-9]+$' | while read d; do echo "${{d#{prefix}}} $d"; done | sort -n | head -n -{retain} | awk '{{print $2}}'); do
  if [ -f "$D/app.pid" ]; then kill "$(cat "$D/app.pid")" 2>/dev/null || true; rm -f "$D/app.pid"; echo "RETIRE $D"; fi
done
"""

    # 把脚本 base64 后作为远端单条命令执行;pty 的 stdin 只用于喂密码,避免与脚本输入冲突
    b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    remote_cmd = f"echo {b64} | base64 -d | bash"
    ssh_argv = [
        "ssh", "-tt",
        "-p", ssh_port,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        "-o", "NumberOfPasswordPrompts=1",
        f"{user}@{host}", remote_cmd,
    ]
    code, raw = _ssh_with_password(ssh_argv, password)
    out = _scrub(raw.strip(), token, password)

    if "DEPLOY_OK" not in out:
        result["reason"] = "远端部署失败:" + out[-800:]
        return result
    result["deployed"] = True
    result["url"] = f"http://{host}:{app_port}/"
    result["workdir"] = workdir
    return result
