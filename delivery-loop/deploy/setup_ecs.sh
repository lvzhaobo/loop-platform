#!/usr/bin/env bash
# loop-platform 一键部署到 ECS(在 ECS 上执行)。
#
# 干什么:装依赖 → 拉/更新代码 → 建 venv+装 Flask → 校验 .env → 自检 →(可选)装 systemd 常驻服务。
# 幂等:可重复执行,已完成的步骤会跳过。
#
# 用法(在 ECS 上):
#   # 首次:克隆 + 装环境(把 <私有仓地址> 换成你的 loop-platform 仓)
#   REPO_URL="https://<token>@github.com/lvzhaobo/loop-platform.git" bash setup_ecs.sh
#
#   # 已有代码目录,只更新 + 自检:
#   APP_DIR=~/loop-platform bash setup_ecs.sh
#
#   # 顺便装常驻按钮服务(需 sudo):
#   APP_DIR=~/loop-platform bash setup_ecs.sh --with-service
#
# 环境变量:
#   APP_DIR      代码目录        (默认 ~/loop-platform)
#   REPO_URL     git 克隆地址    (目录不存在时必填;私有仓建议用带 token 的 https)
#   BRANCH       分支            (默认 main)
#   --with-service  额外渲染并安装 systemd 服务(开机自启 + 崩溃自拉起)
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/loop-platform}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
WITH_SERVICE=0
[ "${1:-}" = "--with-service" ] && WITH_SERVICE=1

say()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[setup] %s\033[0m\n' "$*" >&2; exit 1; }

# --- 需要 root/sudo 才能装系统包 ---
SUDO=""
if [ "$(id -u)" -ne 0 ]; then command -v sudo >/dev/null 2>&1 && SUDO="sudo"; fi

# ---- 1. 系统依赖:python3 / venv / pip / git ----
say "检查系统依赖(python3 / git / venv) ..."
if ! command -v git >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    say "用 apt 安装 git python3 python3-venv python3-pip ..."
    $SUDO apt-get update -y
    $SUDO apt-get install -y git python3 python3-venv python3-pip
  else
    die "缺 git/python3,且非 apt 系统。请先手动安装 git、python3、python3-venv、python3-pip。"
  fi
fi
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
say "python3 版本:$PYV(需 ≥ 3.8)"
python3 -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,8) else 1)' \
  || die "Python 版本过低(需 ≥ 3.8),请升级后重试。"

# ---- 2. 拉/更新代码(三种来源:git 更新 / git 克隆 / 直传就绪) ----
if [ -d "$APP_DIR/.git" ]; then
  say "已存在 git 代码目录,git 更新:$APP_DIR"
  git -C "$APP_DIR" fetch -q origin "$BRANCH"
  git -C "$APP_DIR" checkout -q "$BRANCH"
  git -C "$APP_DIR" reset -q --hard "origin/$BRANCH"
elif [ -n "$REPO_URL" ]; then
  say "克隆代码到 $APP_DIR ..."
  git clone -q -b "$BRANCH" "$REPO_URL" "$APP_DIR"
elif [ -f "$APP_DIR/delivery-loop/run_backlog.sh" ]; then
  # 直传模式:代码已由 sync_to_ecs.py 解包到位,无 .git、也没给 REPO_URL,跳过拉取。
  say "检测到已就绪代码(直传模式,无 .git),跳过拉取:$APP_DIR"
else
  die "目录 $APP_DIR 无代码且未提供 REPO_URL。请 REPO_URL=... bash setup_ecs.sh,或先直传代码到该目录。"
fi
cd "$APP_DIR"

# ---- 3. venv + 依赖(Flask 供验收层真渲染 & 产物运行) ----
say "建立 venv 并安装依赖 ..."
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q flask
say "依赖就绪(flask)。"

# ---- 4. 校验密钥 .env(绝不进 git;需你手动放置) ----
NEED_KEYS=(DEEPSEEK_API_KEY FEISHU_APP_ID FEISHU_APP_SECRET GITHUB_TOKEN)
if [ ! -f .env ]; then
  warn "未发现 $APP_DIR/.env —— 真实模式跑不起来。"
  cat <<EOF

  请在 $APP_DIR/.env 里放置以下键(每行 export KEY=值),然后 chmod 600 .env:
    export DEEPSEEK_API_KEY=...      # 编译/生成用
    export DEEPSEEK_BASE_URL=...     # 可选
    export DEEPSEEK_MODEL=...        # 可选
    export FEISHU_APP_ID=...         # 读飞书文档用
    export FEISHU_APP_SECRET=...
    export GITHUB_TOKEN=...          # 推 loop-sample 用
    # 对外暴露按钮时强烈建议:export HARNESS_TRIGGER_TOKEN=一段随机串

  提示:本机千万别把 .env 提交进 git(仓库 .gitignore 已排除)。
EOF
else
  chmod 600 .env || true
  MISSING=()
  for k in "${NEED_KEYS[@]}"; do grep -qE "^\s*(export\s+)?$k=" .env || MISSING+=("$k"); done
  if [ "${#MISSING[@]}" -gt 0 ]; then
    warn ".env 缺少这些键(真实模式会失败):${MISSING[*]}"
  else
    say ".env 就绪,必需密钥齐全。"
  fi
fi

# ---- 5. 自检:关键文件 + 语法 ----
say "自检:关键入口与脚本 ..."
for f in delivery-loop/run_backlog.sh delivery-loop/orchestrator.py \
         delivery-loop/trigger/webhook.py delivery-loop/trigger/index.html \
         harness-4/studio/server.py harness-4/generate.sh loop-platform/index.html; do
  [ -f "$f" ] || die "缺文件:$f(代码可能不完整)"
done
bash -n delivery-loop/run_backlog.sh
./.venv/bin/python -c "import ast,sys; [ast.parse(open(p).read()) for p in ['delivery-loop/orchestrator.py','delivery-loop/trigger/webhook.py','harness-4/studio/server.py']]"
say "自检通过。"

# ---- 6.(可选)装 systemd 常驻服务(两个:webhook 按钮页 + studio 配置平台) ----
if [ "$WITH_SERVICE" -eq 1 ]; then
  render_unit() {  # $1=服务名 $2=模板路径 → 渲染 __APP_DIR__/__USER__ 后 cp 到 systemd
    local name="$1" tpl="$2" tmp
    [ -f "$tpl" ] || die "缺服务模板:$tpl"
    tmp=$(mktemp)
    sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__USER__#$(id -un)#g" "$tpl" > "$tmp"
    $SUDO cp "$tmp" "/etc/systemd/system/$name.service"
    rm -f "$tmp"
  }
  say "渲染并安装 systemd 服务:loop-platform(:8787 按钮页) + loop-studio(:5100 配置平台) + loop-spa(:5200 SPA 前端) ..."
  render_unit loop-platform delivery-loop/deploy/loop-platform.service
  render_unit loop-studio   delivery-loop/deploy/loop-studio.service
  render_unit loop-spa      delivery-loop/deploy/loop-spa.service
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now loop-platform loop-studio loop-spa
  say "服务已启动。状态:systemctl status loop-platform loop-studio loop-spa | 日志:journalctl -u loop-studio -f"
fi

# ---- 完成 · 打印两种触发方式 ----
PORT="${HARNESS_TRIGGER_PORT:-8787}"
cat <<EOF

============================================================
✅ loop-platform 就绪于 $APP_DIR
------------------------------------------------------------
形态一 · 一条命令(SSH 上来直接跑一批):
  cd $APP_DIR && \\
  HARNESS_BACKLOG_SOURCE=feishu HARNESS_MODE=real HARNESS_AUTOCOMMIT=1 \\
  HARNESS_GIT_PUSH=1 HARNESS_GIT_SUBDIR_AUTO=1 \\
  HARNESS_GIT_REMOTE=github.com/lvzhaobo/loop-sample.git \\
  ./.venv/bin/python delivery-loop/orchestrator.py

形态二 · 一个按钮(webhook 常驻,默认绑 127.0.0.1):
  # 若已 --with-service:服务已在跑。本机验证:
  curl -X POST http://127.0.0.1:$PORT/trigger
  # 从你自己电脑安全访问按钮页(零公网暴露,推荐):
  ssh -L $PORT:127.0.0.1:$PORT <你>@<ECS>
  然后浏览器打开 http://127.0.0.1:$PORT/
  # 要直接公网访问:改 HARNESS_TRIGGER_HOST=0.0.0.0 + 设 HARNESS_TRIGGER_TOKEN + 安全组只放行你的 IP

形态三 · 完整配置平台 studio(--with-service 时常驻,绑 127.0.0.1:5100):
  # 约束/用例编辑 + 一致性预检 + 🚀 开始交付按钮
  ssh -L 5100:127.0.0.1:5100 <你>@<ECS>
  然后浏览器打开 http://127.0.0.1:5100

形态四 · 精美 SPA 前端 loop-spa(--with-service 时常驻,绑 127.0.0.1:5200):
  # Dashboard/需求/Trace/一键交付;SPA 前端打 5100 API,故需同时开两条隧道
  ssh -L 5200:127.0.0.1:5200 -L 5100:127.0.0.1:5100 <你>@<ECS>
  然后浏览器打开 http://127.0.0.1:5200
============================================================
EOF
