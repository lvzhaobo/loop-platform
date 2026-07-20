#!/usr/bin/env bash
# ============================================================
#  push_repos.sh — 建私有仓 + 加 remote + 推送(对外动作,需交互确认)
#  前置:先跑 build_repos.sh 生成 dist-repos/。GITHUB_TOKEN 从仓库根 .env 读。
#  用法: bash delivery-loop/publish/push_repos.sh
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/dist-repos"
OWNER="lvzhaobo"
REPOS=("loop-platform" "loop-specs")   # 均建为私有

# 载入 token(不回显)
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
: "${GITHUB_TOKEN:?未找到 GITHUB_TOKEN(请在仓库根 .env 设置)}"

echo "将执行以下对外动作:"
for r in "${REPOS[@]}"; do echo "  - 在 GitHub 创建【私有】仓 $OWNER/$r 并推送 $OUT/$r"; done
read -r -p "确认继续? (yes/no) " ans
[ "$ans" = "yes" ] || { echo "已取消。"; exit 0; }

api() { curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" \
             -H "Accept: application/vnd.github+json" "$@"; }

for r in "${REPOS[@]}"; do
  dir="$OUT/$r"
  [ -d "$dir/.git" ] || { echo "✗ $dir 未组装,请先跑 build_repos.sh"; exit 1; }

  echo "==> 创建私有仓 $OWNER/$r"
  code=$(api -o /tmp/gh_create.json -w '%{http_code}' \
      -X POST https://api.github.com/user/repos \
      -d "{\"name\":\"$r\",\"private\":true,\"auto_init\":false}")
  if [ "$code" = "201" ]; then echo "  ✅ 已创建"
  elif [ "$code" = "422" ]; then echo "  ⚠ 已存在,复用"
  else echo "  ✗ 创建失败(HTTP $code):"; cat /tmp/gh_create.json; exit 1; fi

  echo "==> 推送 $r"
  ( cd "$dir"
    git remote remove origin 2>/dev/null || true
    git remote add origin "https://${GITHUB_TOKEN}@github.com/$OWNER/$r.git"
    git -c http.version=HTTP/1.1 push -u origin main
    git remote set-url origin "https://github.com/$OWNER/$r.git"   # 抹掉 URL 里的 token
  )
  echo "  ✅ https://github.com/$OWNER/$r"
done
echo "完成。"
