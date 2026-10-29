#!/usr/bin/env bash
# Sample B：用 DSH 跑同一份任务、同一个门禁。
# 三个装置里，这一条命令就是"装置"的全部差别。
set -uo pipefail
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════"
echo " ① 先看门禁现状（裁判先说话）"
echo "═══════════════════════════════════════════════════"
python3 shared/check.py
BEFORE=$?
echo "   当前门禁退出码 = $BEFORE"

echo
echo "═══════════════════════════════════════════════════"
echo " ② 用 DSH headless 跑同一份 tasks.md"
echo "   （改这一行 → 就换成了 IDE 或 Sample A 那个装置）"
echo "═══════════════════════════════════════════════════"
dsh --profile headless "$(cat shared/tasks.md)"
AGENT=$?
echo "   agent 退出码 = $AGENT"

echo
echo "═══════════════════════════════════════════════════"
echo " ③ 再跑门禁 —— 这才是能不能合并的依据"
echo "═══════════════════════════════════════════════════"
python3 shared/check.py
GATE=$?

echo
echo "═══════════════════════════════════════════════════"
echo " 结论：agent=$AGENT  门禁=$GATE"
echo "       ✅ 仅当 agent=0 且 门禁=0 才允许合并"
echo "       ⚠️ agent 说「我完成了」不算数，门禁说了算"
echo "═══════════════════════════════════════════════════"
exit $GATE
