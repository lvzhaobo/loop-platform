#!/usr/bin/env bash
# delivery-loop 主入口:从需求池自主取任务 → 调 harness-4 引擎 → 回写状态。
# 默认 sample 模式(零密钥)。real 模式需在仓库根 .env 配 DEEPSEEK_API_KEY。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DL="delivery-loop"

source "$DL/config.env"
# 所有密钥(DEEPSEEK_API_KEY / GITHUB_TOKEN / ECS_SSH_PASSWORD / FEISHU_APP_*)统一从仓库根 .env 读取(已 gitignore)
[ -f .env ] && set -a && source .env && set +a

# 选择 Python 解释器:优先仓库 .venv(依赖齐全),其次 python3,最后 python
# macOS 通常无裸 python,故不能直接用 python
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  PYTHON="$(command -v python)"
fi
"$PYTHON" "$DL/orchestrator.py" "$@"
