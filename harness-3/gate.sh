#!/usr/bin/env bash
# Harness-3 门禁(⑧):约束自洽性 → 全用例生成验证闭环。
# 任一环节失败即返回非 0,可挂进 CI 挡住不合格产物的合并。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HDIR="harness-3"

source "$HDIR/config.env"
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

echo "========== 门禁 1/2:约束自洽性检查(⑨) =========="
python "$HDIR/check_consistency.py"

echo "========== 门禁 2/2:全用例生成 + 验证闭环(⑥⑦) =========="
bash "$HDIR/generate.sh"

echo "🎉 门禁全部通过:约束自洽 + 全用例验收通过"
