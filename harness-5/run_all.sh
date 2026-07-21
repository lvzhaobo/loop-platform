#!/usr/bin/env bash
# 一键按 L0→L4 顺序跑通全部层(默认 sample 离线模式)。
# 用法: bash harness-5/run_all.sh
set -u
cd "$(dirname "$0")/.."   # 切到仓库根目录
PY=${PYTHON:-python3}

echo "========== L0 单次调用 =========="
$PY harness-5/l0_single/run.py

echo; echo "========== L1 Harness(预期发现 bug,退出码 1) =========="
$PY harness-5/l1_harness/gate.py || echo "(L1 如实报错,符合预期)"

echo; echo "========== L2 Loop(失败回喂 → 修好) =========="
$PY harness-5/l2_loop/loop.py

echo; echo "========== L3 护栏(正常路径) =========="
$PY harness-5/l3_guardrails/loop_guarded.py

echo; echo "========== L3 护栏(STUCK 触发卡死检测) =========="
HARNESS_SAMPLE_STUCK=1 $PY harness-5/l3_guardrails/loop_guarded.py || echo "(护栏触发,符合预期)"

echo; echo "========== L4 确定性(跑两遍比对哈希) =========="
$PY harness-5/l4_determinism/determinism.py

echo; echo "========== L5 LangGraph 编排(需已装 langgraph) =========="
if $PY -c "import langgraph" 2>/dev/null; then
  $PY harness-5/l5_langgraph/run.py
else
  echo "(跳过 L5:未安装 langgraph。装法: pip install -r harness-5/l5_langgraph/requirements.txt)"
fi

echo; echo "全部跑完。产物见 harness-5/output/"
