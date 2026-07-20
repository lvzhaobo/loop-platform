#!/usr/bin/env bash
# =============================================================================
# delivery-loop / trigger / poll.sh —— 轮询式自动触发器(Polling-based Loop)
# -----------------------------------------------------------------------------
# 作用:把"人手动跑 run_backlog.sh"升级为"系统主动、周期性地跑",
#       这就是 Loop Engineering 里唯一真正新增的能力 —— Self-Triggering(自触发)。
#
# 定位:纯外挂。本脚本只做一件事——**子进程调用 run_backlog.sh**,
#       不 import orchestrator.py,不碰 harness-4/5 的任何代码或产物。
#       需求怎么取、引擎怎么跑、状态怎么回写,全都还是原班人马,一行未改。
#
# 两种用法(二选一):
#   1) 守护进程模式(默认):自己 while 循环,每隔 N 秒扫一次需求池,适合前台/长驻。
#        bash delivery-loop/trigger/poll.sh
#   2) 单次模式(--once):只扫一批就退出,适合交给系统 crontab 定时拉起。
#        bash delivery-loop/trigger/poll.sh --once
#        # crontab 示例(每 5 分钟一次,日志追加到文件):
#        # */5 * * * * cd /绝对路径/demo-2 && bash delivery-loop/trigger/poll.sh --once >> /tmp/dl-poll.log 2>&1
#
# 并发锁:两种模式都用一把基于 mkdir 的原子锁,防止"上一批还没跑完,下一批又被拉起"
#         导致同一 case 并行生成、产物互相踩踏。拿不到锁就跳过本轮(而不是排队堆积)。
#
# 环境变量(见 config.env,均可被外部导出覆盖):
#   HARNESS_TRIGGER_INTERVAL  守护进程模式下两次扫描的间隔秒数(默认 300)
#   其余(HARNESS_MODE / HARNESS_BACKLOG_SOURCE / HARNESS_AUTOCOMMIT ...)原样透传给 run_backlog.sh
# =============================================================================
set -euo pipefail

# --- 定位路径:trigger/ 的上一级是 delivery-loop,再上一级是仓库根 ---
TRIGGER_DIR="$(cd "$(dirname "$0")" && pwd)"
DL_DIR="$(cd "$TRIGGER_DIR/.." && pwd)"
ROOT="$(cd "$DL_DIR/.." && pwd)"
cd "$ROOT"

# --- 读配置拿到轮询间隔(config.env 里带默认值,这里再兜底一次)---
# shellcheck disable=SC1091
source "$DL_DIR/config.env"
INTERVAL="${HARNESS_TRIGGER_INTERVAL:-300}"

# --- 并发锁:mkdir 是原子操作,创建成功=拿到锁;失败=已有一批在跑 ---
LOCK_DIR="$DL_DIR/.trigger.lock"

acquire_lock() {
  # 返回 0=拿到锁;返回 1=没拿到(说明上一批还在跑)
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    # 记下持锁进程 pid,方便排查卡死
    echo "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  return 1
}

release_lock() {
  rm -rf "$LOCK_DIR"
}

# 跑一批需求池:拿锁 → 调 run_backlog.sh → 无论成败都释放锁
run_once() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  if ! acquire_lock; then
    echo "[poll $ts] 上一批仍在运行(锁 $LOCK_DIR 被占),本轮跳过。"
    return 0
  fi
  # 用 trap 保证即使 run_backlog.sh 异常退出也会释放锁,不会把自己永久锁死
  trap release_lock EXIT
  echo "[poll $ts] ▶ 触发一批:bash $DL_DIR/run_backlog.sh"
  # 关键:纯子进程调用,把当前环境(含各开关)透传下去;失败不让 set -e 掀翻循环
  bash "$DL_DIR/run_backlog.sh" || echo "[poll $ts] ⚠ run_backlog.sh 返回非 0(见上方引擎日志)"
  trap - EXIT
  release_lock
  echo "[poll $(date '+%H:%M:%S')] ✔ 本批结束。"
}

# --- 主流程:单次 vs 守护进程 ---
if [[ "${1:-}" == "--once" ]]; then
  # crontab 场景:系统负责"周期",本脚本只管"跑一次"
  run_once
  exit 0
fi

# 守护进程场景:自己负责"周期"。Ctrl-C 时清理锁再退出。
trap 'echo; echo "[poll] 收到退出信号,清理锁并停止。"; release_lock; exit 0' INT TERM
echo "[poll] 守护进程启动:每 ${INTERVAL}s 扫一次需求池(Ctrl-C 停止)。"
echo "[poll] 来源=${HARNESS_BACKLOG_SOURCE:-local} 模式=${HARNESS_MODE:-sample}"
while true; do
  run_once
  sleep "$INTERVAL"
done
