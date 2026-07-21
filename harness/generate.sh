#!/usr/bin/env bash
set -e
MAX_RETRY=3
TS=$(date +%Y%m%d-%H%M%S)
OUT="output/$TS"
mkdir -p "$OUT"
echo "本次产物目录:$OUT"

# 读取密钥(DEEPSEEK_API_KEY 等)。优先已导出的环境变量,否则加载 .env
[ -z "$DEEPSEEK_API_KEY" ] && [ -f .env ] && source .env

# 失败→反馈→自动重生成 的闭环(Harness 灵魂,禁止只跑一次)
FEEDBACK=""
for i in $(seq 1 $MAX_RETRY); do
  echo "=== 第 $i 次生成 ==="
  # 真实生成:DeepSeek 依据 prompt.md + rules/ + spec/ 生成到 $OUT;
  # 非首次时把上一轮 _verify.log 作为反馈传入,只修复失败项。
  python harness/run_model.py "$OUT" $FEEDBACK
  if python harness/verify.py "$OUT" | tee "$OUT/_verify.log"; then
    echo "✅ 第 $i 次通过"; exit 0
  fi
  echo "❌ 第 $i 次未通过,带反馈重生成"
  FEEDBACK="$OUT/_verify.log"
done
echo "达最大重试仍未通过 → 回到 rules/ 或 spec/ 加强约束(改约束,不改产物)"; exit 1
