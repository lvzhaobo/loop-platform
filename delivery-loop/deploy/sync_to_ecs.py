#!/usr/bin/env python3
"""本地一次性运行:把 loop 平台代码直传到 ECS 并安装常驻服务(不经 GitHub)。

为什么不用 sshpass/paramiko:sshpass 在 macOS 难装,paramiko 在 Python 3.14 无预编译包。
这里复用 deployer.py 的做法——用标准库 pty 驱动系统 ssh/scp,在出现口令提示时喂一次密码。

用法(在仓库根执行):
  .venv/bin/python delivery-loop/deploy/sync_to_ecs.py probe   # 阶段0:只读勘查 ECS 现状
  .venv/bin/python delivery-loop/deploy/sync_to_ecs.py sync    # 阶段2:打包 + 传输 + 远端安装

凭证:从仓库根 .env 读 ECS_SSH_PASSWORD(必填)。
主机:默认 47.76.211.100 / root / 22,可用环境变量 ECS_HOST / ECS_SSH_USER / ECS_SSH_PORT 覆盖。
所有输出中的密码不打印明文(替换为 ****)。
"""
from __future__ import annotations

import base64
import os
import pty
import select
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP_DIR = "/root/loop-platform"          # ECS 上的代码目录(与 OPS.md 一致)
TARBALL = "/tmp/loop-platform-xfer.tar.gz"  # 传输用临时压缩包(本地与远端同名)
REMOTE_ENV = "/tmp/loop-platform.env"    # .env 落地前的远端临时路径

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=15",
    "-o", "NumberOfPasswordPrompts=1",
]


def load_env(path: str) -> None:
    """把仓库根 .env 里的 export KEY=VAL / KEY=VAL 读进 os.environ(仅补空缺)。"""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _emit(data: bytes, password: str) -> None:
    """把子进程输出实时打到屏幕,顺手抹掉可能回显的密码。"""
    text = data.decode("utf-8", "replace")
    if password:
        text = text.replace(password, "****")
    sys.stdout.write(text)
    sys.stdout.flush()


def run_with_password(argv: list[str], password: str, timeout: int = 900) -> int:
    """用 pty 运行 argv,在出现 'assword' 提示时喂一次密码;实时回显输出直到结束。"""
    pid, fd = os.forkpty()
    if pid == 0:  # 子进程:执行 ssh/scp
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
            _emit(data, password)
            if not sent and b"assword" in out:  # 匹配 password:/Password:
                os.write(fd, password.encode() + b"\n")
                sent = True
    try:
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        return 0


def ssh_run(script: str, host: str, user: str, port: str, password: str,
            timeout: int = 900) -> int:
    """把 shell 脚本 base64 后作为远端单条命令执行(pty 的 stdin 只用于喂密码)。"""
    b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    remote_cmd = f"echo {b64} | base64 -d | bash"
    argv = ["ssh", "-tt", "-p", port, *SSH_OPTS, f"{user}@{host}", remote_cmd]
    return run_with_password(argv, password, timeout)


def scp_up(local: str, remote: str, host: str, user: str, port: str,
           password: str, timeout: int = 900) -> int:
    argv = ["scp", "-P", port, *SSH_OPTS, local, f"{user}@{host}:{remote}"]
    return run_with_password(argv, password, timeout)


def build_tarball() -> None:
    """打包 delivery-loop/ harness-4/ loop-platform/index.html,排除虚拟环境/产物/缓存。"""
    print(f"[sync] 打包代码 -> {TARBALL}")
    argv = [
        "tar", "czf", TARBALL, "-C", ROOT,
        "--exclude", ".venv",
        "--exclude", "output",
        "--exclude", ".git",
        "--exclude", "__pycache__",
        "--exclude", "*.pyc",
        "--exclude", "feishu_state.json.bak.*",
        "--exclude", "feishu_state.json.damaged.*",
        "--exclude", "feishu_state.json.pre-*",
        "delivery-loop", "harness-4", "loop-platform/index.html",
    ]
    subprocess.run(argv, check=True)
    size = os.path.getsize(TARBALL)
    print(f"[sync] 压缩包就绪:{size/1024:.0f} KB")


PROBE_SCRIPT = r"""
echo "== whoami =="; whoami
echo "== os =="; (. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")
echo "== python3 =="; python3 --version 2>&1 || echo "(无 python3)"
echo "== git =="; git --version 2>&1 || echo "(无 git)"
echo "== 代码目录 /root/loop-platform =="; ls -la /root/loop-platform 2>/dev/null | head || echo "(不存在)"
echo "== 现有 .env =="; ls -la /root/loop-platform/.env 2>/dev/null || echo "(无)"
echo "== 现有 feishu_state.json =="; ls -la /root/loop-platform/delivery-loop/backlog/feishu_state.json 2>/dev/null || echo "(无)"
echo "== loop-* systemd 服务 =="; systemctl list-unit-files 2>/dev/null | grep -E "loop-" || echo "(无 loop-* 服务)"
echo "== 运行中的 sample(勿动) =="; ls -d ~/apps/loop-sample/sample*/ 2>/dev/null || echo "(无)"
echo "== 端口 5100/8787/5200 占用 =="; ss -ltnp 2>/dev/null | grep -E ":5100|:8787|:5200" || echo "(均空闲)"
"""


def remote_install_script() -> str:
    """远端安装(面向已存在的生产部署,最小惊讶):
    备份密钥与运行态 -> 停用 .git(让直传代码权威,可回滚)
    -> 解包最新代码 -> 还原 ECS 侧运行态(去重账本/需求清单)
    -> 跑 setup_ecs.sh --with-service -> 重启三服务拉新代码。
    注:不覆盖已有 .env(保留 ECS 在用的),不动 ~/apps/loop-sample 的运行样例。"""
    bk = "$APP/delivery-loop/backlog"
    return f"""set -e
APP={APP_DIR}
TS=$(date +%s)
mkdir -p "$APP"
cd "$APP"
# 1) 备份密钥与运行态(不覆盖:.env 保留 ECS 在用的;账本/清单稍后还原)
[ -f .env ] && cp .env .env.bak.$TS && echo "[remote] 已备份 .env -> .env.bak.$TS"
for f in feishu_state.json feishu_docs.json; do
  [ -f "{bk}/$f" ] && cp "{bk}/$f" "{bk}/$f.bak.$TS" && echo "[remote] 已备份 $f"
done
# 2) 停用 .git,避免 setup_ecs.sh 走 git reset --hard 把直传的最新代码回滚到陈旧 GitHub 版本
[ -d .git ] && mv .git ".git.disabled.$TS" && echo "[remote] 已停用 .git -> .git.disabled.$TS(直传模式权威,可回滚)"
# 3) 解包最新代码(覆盖 delivery-loop / harness-4 / loop-platform/index.html)
tar xzf {TARBALL} -C "$APP"
echo "[remote] 最新代码已解包到 $APP"
# 4) 还原 ECS 侧运行态:去重账本 + 需求清单(保住已部署样例追踪不丢失)
for f in feishu_state.json feishu_docs.json; do
  [ -f "{bk}/$f.bak.$TS" ] && cp "{bk}/$f.bak.$TS" "{bk}/$f" && echo "[remote] 已还原 ECS 侧 $f"
done
rm -f {TARBALL}
# 5) 安装(直传模式:无 .git -> 跳过拉取;建/复用 venv、装三个 systemd 服务)
bash delivery-loop/deploy/setup_ecs.sh --with-service
# 6) 重启三服务以加载最新代码(enable --now 不会重启已在跑的服务)
systemctl restart loop-studio loop-platform loop-spa || true
sleep 2
echo "[remote] ===== 服务状态 ====="
systemctl is-active loop-studio loop-platform loop-spa || true
"""


def main() -> int:
    load_env(os.path.join(ROOT, ".env"))
    host = os.environ.get("ECS_HOST", "").strip() or "47.76.211.100"
    user = os.environ.get("ECS_SSH_USER", "root").strip() or "root"
    port = os.environ.get("ECS_SSH_PORT", "22").strip() or "22"
    password = os.environ.get("ECS_SSH_PASSWORD", "")

    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode not in ("probe", "sync"):
        print(f"未知模式 {mode!r};用法:sync_to_ecs.py [probe|sync]")
        return 2
    if not password:
        print("缺少 ECS_SSH_PASSWORD(仓库根 .env 未配置),无法连接 ECS。")
        return 2

    print(f"[sync] 目标 ECS = {user}@{host}:{port}  代码目录 = {APP_DIR}")

    if mode == "probe":
        print("[sync] 阶段0:只读勘查 ECS 现状 ...")
        return ssh_run(PROBE_SCRIPT, host, user, port, password, timeout=120)

    # mode == "sync"
    # 注:不传 .env——ECS 已有在用的密钥文件(与本地同钥),保留以免回归。
    build_tarball()
    print("[sync] 传输压缩包 ...")
    if scp_up(TARBALL, TARBALL, host, user, port, password) != 0:
        print("[sync] 压缩包传输失败,中止。")
        return 1
    print("[sync] 远端解包 + 安装 + 装服务 ...")
    code = ssh_run(remote_install_script(), host, user, port, password, timeout=1200)
    # 清理本地临时压缩包
    try:
        os.remove(TARBALL)
    except OSError:
        pass
    print(f"[sync] 完成,远端退出码 = {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
