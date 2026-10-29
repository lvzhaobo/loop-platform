#!/usr/bin/env bash
# 启动演示控制台
#   ./start.sh            离线 mock（不需要 API key）
#   ./start.sh --real     真实模型（先在 config.env 填 DEEPSEEK_API_KEY）
set -uo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "--real" ]; then
  python3 server.py
else
  echo "  离线模式（用 --real 可切真实模型）"
  python3 server.py --mock
fi
