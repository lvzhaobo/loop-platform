#!/usr/bin/env python3
"""在 ECS 上执行一段 shell 脚本(复用 sync_to_ecs 的 pty+口令机制,不落密码明文)。

用途:运维/交付时需要在 ECS 上跑一次性命令(勘查状态、触发交付、验证结果),
     又不想把凭证散落各处。脚本从文件读取(避免多行转义地狱),base64 后远端执行。

用法(在仓库根执行):
  .venv/bin/python delivery-loop/deploy/ecs_exec.py <脚本文件路径> [超时秒]

凭证:从仓库根 .env 读 ECS_HOST / ECS_SSH_PASSWORD;用户/端口默认 root/22,
     可用 ECS_HOST / ECS_SSH_USER / ECS_SSH_PORT 覆盖(与 sync_to_ecs 一致)。
"""
from __future__ import annotations

import os
import sys

# 复用同目录 sync_to_ecs 的 load_env / ssh_run(pty 喂密码、密码打码回显)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_to_ecs import ROOT, load_env, ssh_run  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法:ecs_exec.py <脚本文件路径> [超时秒]")
        return 2
    script_path = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    if not os.path.isfile(script_path):
        print(f"脚本文件不存在:{script_path}")
        return 2
    with open(script_path, encoding="utf-8") as f:
        script = f.read()

    # .env 优先取 ROOT(loop/)，其次取上一级(工作区根,本地开发布局)
    env_path = os.path.join(ROOT, ".env")
    if not os.path.isfile(env_path):
        env_path = os.path.join(os.path.dirname(ROOT), ".env")
    load_env(env_path)
    host = os.environ.get("ECS_HOST", "").strip()
    user = os.environ.get("ECS_SSH_USER", "root").strip() or "root"
    port = os.environ.get("ECS_SSH_PORT", "22").strip() or "22"
    password = os.environ.get("ECS_SSH_PASSWORD", "")
    if not host:
        print("缺少 ECS_HOST(仓库根 .env 未配置目标服务器地址),无法连接。")
        return 2
    if not password:
        print("缺少 ECS_SSH_PASSWORD(仓库根 .env 未配置),无法连接 ECS。")
        return 2

    print(f"[ecs_exec] {user}@{host}:{port}  脚本={script_path}  超时={timeout}s")
    return ssh_run(script, host, user, port, password, timeout)


if __name__ == "__main__":
    raise SystemExit(main())
