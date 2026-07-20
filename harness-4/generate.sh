#!/usr/bin/env bash
# Harness-4 生成闭环(多用例回归 + 失败反馈重试 + 确定性复跑校验)。
# 对每个用例:生成→验证→失败带反馈重生成;通过后复跑一次比对产物哈希;记录运行历史。
# 支持 HARNESS_MODE=sample 离线模式(不烧额度,产物确定性,用于冒烟/CI)。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HDIR="harness-4"
MAX_RETRY=5

# 载入确定性配置与密钥
source "$HDIR/config.env"
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

# 用例集:优先环境变量 HARNESS_CASES;否则用 constraints.json 的 run_cases(默认运行集);
# run_cases 缺省时回退到 cases(全部已登记用例)。仅影响「实际运行」,不影响自洽检查/Schema 派生。
CASES="${HARNESS_CASES:-$(python -c "import json;c=json.load(open('$HDIR/constraints.json'));print(' '.join(c.get('run_cases') or c['cases']))")}"
TS=$(date +%Y%m%d-%H%M%S)
echo "本次批次:$TS  模式:${HARNESS_MODE:-real}  回归用例:$CASES"

# 产物代码指纹(排除元数据/缓存/报告/占位图,用于确定性比对)
hash_out() {
  ( cd "$1" && find . -type f \
      -not -name '_run_meta.json' -not -name '_verify.log' \
      -not -path './reports/*' \
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
    python "$HDIR/tools/run_model.py" "$CASE" "$OUT" $FEEDBACK
    # 注意:verify 的退出码不能被管道末端的 tee 吞掉,用 PIPESTATUS[0] 取 verify 本身的退出码
    set +e
    python "$HDIR/tools/verify.py" "$CASE" "$OUT" 2>&1 | tee -a "$OUT/_verify.log"
    VSTATUS=${PIPESTATUS[0]}
    set -e
    if [ "$VSTATUS" = "0" ]; then
      echo "✅ [$CASE] 第 $i 次通过"; RESULT="pass"; break
    fi
    echo "❌ [$CASE] 第 $i 次未通过,带反馈重生成"
    FEEDBACK="$OUT/_verify.log"
    # sample 模式产物确定性,重试无意义,直接跳出
    [ "${HARNESS_MODE:-real}" = "sample" ] && break
  done

  # 确定性复跑:通过后复跑一次,比对产物代码指纹
  DET="skip"
  if [ "$RESULT" = "pass" ] && [ "${HARNESS_DET_CHECK:-0}" = "1" ]; then
    OUT2="$OUT-rerun"; mkdir -p "$OUT2"
    echo "--- [$CASE] 确定性复跑 → $OUT2 ---"
    python "$HDIR/tools/run_model.py" "$CASE" "$OUT2"
    H1=$(hash_out "$OUT"); H2=$(hash_out "$OUT2")
    if [ "$H1" = "$H2" ]; then
      DET="identical"; echo "✅ [$CASE] 确定性:两次产物字节一致"
    else
      DET="drift"; echo "⚠️  [$CASE] 确定性告警:两次产物不一致(LLM seed 非严格可复现,已由验证层兜底)"
    fi
  fi

  # 运行历史(可观测):通过率/重试次数/确定性/模式/模型
  printf '{"ts":"%s","case":"%s","dir":"%s","mode":"%s","attempts":%d,"result":"%s","determinism":"%s","model":"%s","seed":%s}\n' \
    "$TS" "$CASE" "$OUT" "${HARNESS_MODE:-real}" "$ATTEMPTS" "$RESULT" "$DET" "${DEEPSEEK_MODEL}" "${HARNESS_SEED:-0}" >> output/runs.jsonl

  [ "$RESULT" = "pass" ] || OVERALL=1
done

echo "运行历史已记入 output/runs.jsonl"
[ "$OVERALL" = "0" ] && echo "✅ 全部回归用例通过" && exit 0
echo "❌ 有用例未通过 → 回到 rules/ 或 cases/*/spec 加强约束(改约束,不改产物)"; exit 1
