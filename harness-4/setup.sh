#!/usr/bin/env bash
# 一键环境准备:创建 venv 并安装验证所需依赖(Flask)。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -d .venv ]; then
  echo "创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null 2>&1 || true
pip install -q "Flask==3.0.*"
echo "✅ 环境就绪(Flask 已安装)。"
echo "下一步:"
echo "  离线冒烟(不烧额度): HARNESS_MODE=sample bash harness-4/gate.sh"
echo "  真实生成:           source .env && bash harness-4/gate.sh"
