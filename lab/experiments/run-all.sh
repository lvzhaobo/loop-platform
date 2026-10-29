#!/usr/bin/env bash
cd "$(dirname "$0")"
set -u
run() { echo; echo "═══ $1 ═══"; }

reset_good() { printf 'def handle(x):\n    if not x:\n        raise Exception("bad")\n    print("debug", x)\n    return {"key": "sk-demo-123456"}\n' > target.txt; }
reset_crash() { printf 'def handle(x):\n    if not x:\n        raise Exception("bad")\n    return {"key": "sk-demo-123456"}\n' > target.txt; }
reset_noop() { printf 'def handle(x):\n    print("debug", x)\n    return {"key": "sk-demo-123456"}\n' > target.txt; }

mkdir -p out; rm -f out/ledger.jsonl

run "试验 1：正常收敛"
reset_good
FIX_MODE=good python3 mumuloop-mini.py run --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 5

run "试验 2：制造回归"
reset_crash
FIX_MODE=crash python3 mumuloop-mini.py run --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 5

run "试验 3：假修 / 不收敛"
reset_noop
FIX_MODE=noop python3 mumuloop-mini.py run --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 6

run "账本汇总"
python3 mumuloop-mini.py stats
