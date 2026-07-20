#!/usr/bin/env bash
# Harness-4 门禁:自洽性 → 派生 Schema → 全用例生成验证闭环。
# 任一环节失败即返回非 0,可挂进 CI 挡住不合格产物的合并。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HDIR="harness-4"

source "$HDIR/config.env"
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

echo "========== 门禁 1/3：spec 为唯一源，校验全用例 case.json 规格字段与 spec 一致 =========="
python "$HDIR/tools/compile_spec.py" --check

echo "========== 门禁 2/3：从事实源派生数据 Schema =========="
python "$HDIR/tools/build_schema.py"

echo "========== 门禁 3/3：全用例生成 + 验证闭环 =========="
bash "$HDIR/generate.sh"

echo "🎉 门禁全部通过：spec→case 派生 + Schema 派生 + 全用例验收通过"
