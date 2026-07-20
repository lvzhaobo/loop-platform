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

python "$DL/orchestrator.py" "$@"
