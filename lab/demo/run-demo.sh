#!/usr/bin/env bash
# 一条命令跑完三个装置（默认 mock，不需要 API key）
#   ./run-demo.sh          跑完自动把 fixture 恢复成"红"状态
#   ./run-demo.sh --keep   跑完不恢复（方便你接着手动改）
set -uo pipefail
cd "$(dirname "$0")"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1
FIX=shared/fixture/pomodoro
BAK=$(mktemp -d)
cp "$FIX"/index.html "$FIX"/app.js "$BAK"/

line(){ printf '\n══════════════════════════════════════════════════════════\n  %s\n══════════════════════════════════════════════════════════\n' "$1"; }

line "0 · 环境"
python3 -V
echo "  配置：$(grep -E '^(DEEPSEEK_MODEL|WORKSPACE|MOCK)=' config.env | tr '\n' '  ')"
echo "  key ：$(grep -q 'sk-在这里' config.env && echo '未填（本次用 mock，不需要）' || echo '已填')"

line "1 · 门禁现状（裁判先说话，应该是红的）"
python3 shared/check.py
echo "  → 退出码 $?"

line "2 · 装置一：自研 harness（离线 mock）"
( cd A-python && python3 main.py --mock --yes )
echo "  → 退出码 $?"

line "3 · 门禁再跑一次（这才是能不能合并的依据）"
python3 shared/check.py
echo "  → 退出码 $?"

if [ "$KEEP" -eq 0 ]; then
  cp "$BAK"/index.html "$BAK"/app.js "$FIX"/
  line "4 · 已把 fixture 恢复成初始状态（门禁重新变红）"
  python3 shared/check.py | tail -2
else
  line "4 · 保留改动（--keep），fixture 现在是改好的版本"
fi

line "5 · 动手实验（学员从这里开始，初始 4/7）"
( cd lab && python3 lab_check.py | tail -6 )

line "下一步"
echo "  真实模型：  填写 config.env 的 DEEPSEEK_API_KEY，然后 cd A-python && python3 main.py"
echo "  安全检查：  cd A-python && WORKSPACE=. python3 main.py --check-safety"
echo "  DSH 装置：  cd B-dsh && ./run.sh      （需要本机装了 dsh）"
echo "  讲师手册：  docs/讲师手册.md"
rm -rf "$BAK"
