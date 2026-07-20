#!/usr/bin/env bash
# ============================================================
#  build_repos.sh — 把 loop-platform / loop-specs 组装到 dist-repos/ 并本地提交
#  安全:排除密钥与运行时状态;只做本地 git commit,不推远端(推送用 push_repos.sh)。
#  用法: bash delivery-loop/publish/build_repos.sh
# ============================================================
set -euo pipefail

# 定位工作区根(本脚本在 <root>/delivery-loop/publish/ 下)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TPL="$HERE/templates"
OUT="$ROOT/dist-repos"
PLATFORM="$OUT/loop-platform"
SPECS="$OUT/loop-specs"

# rsync 排除清单(运行时/密钥/噪音)
EXCLUDES=(
  --exclude '.git' --exclude '.env' --exclude '.env.*'
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv'
  --exclude 'output' --exclude 'dist-repos' --exclude '.DS_Store'
  --exclude '.last_ts' --exclude '*.log'
  --exclude 'backlog/feishu_state.json'
  --exclude 'backlog/feishu_docs.json'
  --exclude 'backlog/backlog.jsonl'
)

echo "==> 清理旧产物 $OUT"
rm -rf "$PLATFORM" "$SPECS"
mkdir -p "$PLATFORM" "$SPECS/cases"

# ---------------- loop-platform ----------------
echo "==> 组装 loop-platform"
rsync -a "${EXCLUDES[@]}" "$ROOT/harness-4"      "$PLATFORM/"
rsync -a "${EXCLUDES[@]}" "$ROOT/delivery-loop"  "$PLATFORM/"

cp "$TPL/platform.README.md"   "$PLATFORM/README.md"
cp "$TPL/platform.gitignore"   "$PLATFORM/.gitignore"
cp "$TPL/platform.env.example" "$PLATFORM/.env.example"

# backlog 只保留 .example(真实态已被 rsync 排除)
mkdir -p "$PLATFORM/delivery-loop/backlog"
cp "$TPL/feishu_docs.example.json" "$PLATFORM/delivery-loop/backlog/feishu_docs.example.json"
cp "$TPL/backlog.example.jsonl"    "$PLATFORM/delivery-loop/backlog/backlog.example.jsonl"

# ---------------- loop-specs ----------------
echo "==> 组装 loop-specs"
for c in "$ROOT"/harness-4/cases/*/; do
  name="$(basename "$c")"
  if [ -d "$c/spec" ]; then
    mkdir -p "$SPECS/cases/$name/spec"
    cp "$c"/spec/*.md "$SPECS/cases/$name/spec/"
  fi
done
[ -f "$ROOT/harness-4/checklist.md" ] && cp "$ROOT/harness-4/checklist.md" "$SPECS/checklist.md"
cp "$TPL/specs.README.md"  "$SPECS/README.md"
cp "$TPL/specs.gitignore"  "$SPECS/.gitignore"

# ---------------- 本地提交 ----------------
commit_repo () {
  local dir="$1" name="$2"
  ( cd "$dir"
    git init -q -b main
    git add -A
    git -c user.name="吕昭波" -c user.email="lvzhaobo@gmail.com" \
        commit -q -m "chore: initial commit of $name"
    echo "  ✅ $name: $(git rev-list --count HEAD) commit, $(git ls-files | wc -l | tr -d ' ') files"
  )
}
echo "==> 本地 git 提交(不推远端)"
commit_repo "$PLATFORM" "loop-platform"
commit_repo "$SPECS"    "loop-specs"

# ---------------- 兜底密钥复检 ----------------
# 注:只扫会真正藏密钥的文件类型(py/js/json/env/txt/yml)。
# .md/.sh 是我们自有的文档与脚本,本就含密钥正则模式说明,不纳入以免误报。
echo "==> 密钥复检"
if grep -rIlE '(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN)' \
     --include='*.py' --include='*.js' --include='*.json' \
     --include='*.env' --include='*.txt' --include='*.yml' --include='*.yaml' \
     "$OUT" 2>/dev/null | grep -v example; then
  echo "  ❌ 发现疑似真实密钥,请清理后再发布!" ; exit 1
fi
if find "$OUT" -name '.env' -not -name '.env.example' | grep -q .; then
  echo "  ❌ 发现 .env 混入!" ; exit 1
fi
echo "  ✅ 无真实密钥、无 .env 混入"
echo ""
echo "完成。产物在: $OUT"
echo "下一步(确认后):bash delivery-loop/publish/push_repos.sh"
