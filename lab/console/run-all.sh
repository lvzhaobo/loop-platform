#!/usr/bin/env bash
# 一键起服务 + 跑全部自检
set -uo pipefail
cd "$(dirname "$0")"
pkill -f "app.py" 2>/dev/null; sleep 0.5
python3 app.py > /tmp/platform.log 2>&1 &
sleep 2
FAIL=0
for f in verify.py verify_specs.py verify_pipeline.py verify_workspace.py; do
  echo "──── $f ────"
  python3 "$f" | tail -5 || FAIL=1
done
pkill -f "app.py" 2>/dev/null
exit $FAIL
