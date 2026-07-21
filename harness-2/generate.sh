#!/usr/bin/env bash
# Harness-2 生成闭环:生成→验证→失败带反馈重生成;记录确定性日志与运行历史。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HDIR="harness-2"
MAX_RETRY=3

# 载入确定性配置与密钥
source "$HDIR/config.env"
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

TS=$(date +%Y%m%d-%H%M%S)
OUT="output/$TS"
mkdir -p "$OUT"
echo "本次产物目录:$OUT"

RESULT="fail"; ATTEMPTS=0; FEEDBACK=""
for i in $(seq 1 $MAX_RETRY); do
  ATTEMPTS=$i
  echo "=== 第 $i 次生成 ==="
  # 真实生成:DeepSeek 依据 base+task+spec 生成;run_model 会写 _verify.log 头部(确定性元数据)
  python "$HDIR/run_model.py" "$OUT" $FEEDBACK
  # 验证结果追加到 _verify.log(-a 保留头部元数据)
  if python "$HDIR/verify.py" "$OUT" | tee -a "$OUT/_verify.log"; then
    echo "✅ 第 $i 次通过"; RESULT="pass"; break
  fi
  echo "❌ 第 $i 次未通过,带反馈重生成"
  FEEDBACK="$OUT/_verify.log"
done

# ⑤ 可观测:运行历史(通过率/重试次数/模型)追加到 output/runs.jsonl
MODEL_USED="${DEEPSEEK_MODEL}"
printf '{"ts":"%s","dir":"%s","attempts":%d,"result":"%s","model":"%s","seed":%s}\n' \
  "$TS" "$OUT" "$ATTEMPTS" "$RESULT" "$MODEL_USED" "${HARNESS_SEED:-0}" >> output/runs.jsonl
echo "运行历史已记入 output/runs.jsonl"

[ "$RESULT" = "pass" ] && exit 0
echo "达最大重试仍未通过 → 回到 rules/ 或 spec/ 加强约束(改约束,不改产物)"; exit 1
