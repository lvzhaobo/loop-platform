#!/usr/bin/env bash
# Harness-3 生成闭环(多用例回归 + 确定性复跑校验)。
# 对每个用例:生成→验证→失败带反馈重生成;通过后复跑一次比对产物哈希;记录运行历史。
set -e
# pipefail:确保 `verify.py | tee` 中 verify 的非 0 退出不被 tee 掩盖(否则会假通过)
set -o pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HDIR="harness-3"
MAX_RETRY=3

# 载入确定性配置与密钥
source "$HDIR/config.env"
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

# ⑦ 用例集:优先环境变量,回退到 constraints.json
CASES="${HARNESS_CASES:-$(python -c "import json;print(' '.join(json.load(open('$HDIR/constraints.json'))['cases']))")}"
TS=$(date +%Y%m%d-%H%M%S)
echo "本次批次:$TS  回归用例:$CASES"

# 产物代码指纹(排除元数据/缓存/占位图,用于确定性比对)
hash_out() {
  ( cd "$1" && find . -type f \
      -not -name '_run_meta.json' -not -name '_verify.log' \
      -not -path './__pycache__/*' -not -path './tests/__pycache__/*' \
      -not -path './static/img/*' | sort \
      | while read -r f; do shasum -a 256 "$f"; done ) | shasum -a 256 | awk '{print $1}'
}

OVERALL=0
for CASE in $CASES; do
  OUT="output/$TS-$CASE"
  mkdir -p "$OUT"
  echo "=== 用例 [$CASE] → $OUT ==="
  RESULT="fail"; ATTEMPTS=0; FEEDBACK=""
  for i in $(seq 1 $MAX_RETRY); do
    ATTEMPTS=$i
    echo "--- [$CASE] 第 $i 次生成 ---"
    python "$HDIR/run_model.py" "$CASE" "$OUT" $FEEDBACK
    if python "$HDIR/verify.py" "$CASE" "$OUT" | tee -a "$OUT/_verify.log"; then
      echo "✅ [$CASE] 第 $i 次通过"; RESULT="pass"; break
    fi
    echo "❌ [$CASE] 第 $i 次未通过,带反馈重生成"
    FEEDBACK="$OUT/_verify.log"
  done

  # ⑥ 确定性复跑:通过后复跑一次,比对产物代码指纹
  DET="skip"
  if [ "$RESULT" = "pass" ] && [ "${HARNESS_DET_CHECK:-0}" = "1" ]; then
    OUT2="$OUT-rerun"; mkdir -p "$OUT2"
    echo "--- [$CASE] 确定性复跑 → $OUT2 ---"
    python "$HDIR/run_model.py" "$CASE" "$OUT2"
    H1=$(hash_out "$OUT"); H2=$(hash_out "$OUT2")
    if [ "$H1" = "$H2" ]; then
      DET="identical"; echo "✅ [$CASE] 确定性:两次产物字节一致"
    else
      DET="drift"; echo "⚠️  [$CASE] 确定性告警:两次产物不一致(LLM seed 非严格可复现,已由验证层兜底)"
    fi
  fi

  # 运行历史(可观测):通过率/重试次数/确定性/模型
  printf '{"ts":"%s","case":"%s","dir":"%s","attempts":%d,"result":"%s","determinism":"%s","model":"%s","seed":%s}\n' \
    "$TS" "$CASE" "$OUT" "$ATTEMPTS" "$RESULT" "$DET" "${DEEPSEEK_MODEL}" "${HARNESS_SEED:-0}" >> output/runs.jsonl

  [ "$RESULT" = "pass" ] || OVERALL=1
done

echo "运行历史已记入 output/runs.jsonl"
[ "$OVERALL" = "0" ] && echo "✅ 全部回归用例通过" && exit 0
echo "❌ 有用例未通过 → 回到 rules/ 或 cases/*/spec 加强约束(改约束,不改产物)"; exit 1
