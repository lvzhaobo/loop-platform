<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { CheckStatus, Profile, RunSummary } from '../api/contracts'
import StatusBadge from '../components/StatusBadge.vue'

const runs = ref<RunSummary[]>([])
const profiles = ref<Profile[]>([])
const error = ref('')
const loading = ref(true)

type Tone = 'ok' | 'bad' | 'warn' | 'muted'
const STATUS_META: Record<CheckStatus, { label: string; tone: Tone; path: string }> = {
  passed: { label: '通过', tone: 'ok', path: 'M9 12.5l2 2 4-4.5' },
  failed: { label: '失败', tone: 'bad', path: 'M7 7l10 10M17 7L7 17' },
  unavailable: { label: '不可用', tone: 'muted', path: 'M5 12h14' },
  indeterminate: { label: '未定', tone: 'warn', path: 'M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.9.4-1.4 1-1.4 1.9' },
  skipped: { label: '跳过', tone: 'muted', path: 'M5 12h13M13 6l6 6-6 6' },
}

const counts = computed(() => (Object.keys(STATUS_META) as CheckStatus[]).map(status => ({
  status, ...STATUS_META[status],
  count: runs.value.filter(r => r.status === status).length,
})))

const stats = computed(() => {
  const total = runs.value.length
  const passed = runs.value.filter(r => r.status === 'passed').length
  const validProfiles = profiles.value.filter(p => p.valid).length
  const events = runs.value.reduce((n, r) => n + r.event_count, 0)
  return { total, passRate: total ? Math.round((passed / total) * 100) : null, validProfiles, events }
})

onMounted(async () => {
  try { const [r, p] = await Promise.all([api.runs(), api.profiles()]); runs.value = r.runs; profiles.value = p.profiles }
  catch (e) { error.value = e instanceof Error ? e.message : '无法读取正式 Studio 数据' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page dash">
    <!-- 首屏 hero -->
    <div class="dash-hero">
      <div class="dash-hero-copy">
        <p class="eyebrow">OFFICIAL LOOP STUDIO</p>
        <h1>交付事实，而非猜测。</h1>
        <p class="lede">正式界面只显示 Profile、冻结 Run Plan 与已验证事件/证据投影。每一个数字都来自可回放的 RunEvent，而不是推断。</p>
        <div class="dash-hero-actions">
          <RouterLink class="primary-button" to="/plans">创建安全 Run Plan</RouterLink>
          <RouterLink class="ghost-button" to="/panorama">查看整体架构图</RouterLink>
        </div>
      </div>
      <div class="dash-hero-stats">
        <div class="stat"><b>{{ loading ? '—' : stats.total }}</b><span>运行总数</span></div>
        <div class="stat"><b>{{ loading ? '—' : (stats.passRate === null ? '—' : stats.passRate + '%') }}</b><span>通过率</span></div>
        <div class="stat"><b>{{ loading ? '—' : stats.validProfiles }}</b><span>有效 Profile</span></div>
        <div class="stat"><b>{{ loading ? '—' : stats.events }}</b><span>已验证事件</span></div>
      </div>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}；未显示 Mock 替代数据。</p>

    <!-- 状态指标卡 -->
    <section class="dash-metrics">
      <article v-for="item in counts" :key="item.status" class="dash-metric" :class="'tone-' + item.tone">
        <div class="dash-metric-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="item.path" /></svg>
        </div>
        <div class="dash-metric-body">
          <span>{{ item.label }}</span>
          <b>{{ loading ? '—' : item.count }}</b>
        </div>
      </article>
    </section>

    <!-- 已验证运行 -->
    <section class="dash-panel">
      <div class="dash-panel-head">
        <div>
          <h2>已验证运行</h2>
          <span>{{ loading ? '正在读取…' : `${runs.length} 条运行 · ${stats.validProfiles} 个有效 Profile` }}</span>
        </div>
        <RouterLink to="/runs" class="text-link">查看全部 →</RouterLink>
      </div>

      <p v-if="!loading && !runs.length" class="empty-state">当前没有 RunEvent 记录；这不代表曾经的兼容历史通过。</p>

      <div v-else class="dash-run-list">
        <RouterLink v-for="run in runs.slice(0, 6)" :key="run.run_id" :to="`/runs/${run.run_id}`" class="dash-run">
          <span class="dash-run-icon">↻</span>
          <div class="dash-run-id"><b>{{ run.run_id }}</b><small>{{ run.last_occurred_at || '未记录时间' }}</small></div>
          <div class="dash-run-badges"><StatusBadge :status="run.status" /><StatusBadge :status="run.integrity" /></div>
          <span class="dash-run-events">{{ run.event_count }} events</span>
        </RouterLink>
        <p v-if="loading" class="dash-loading">正在读取运行记录…</p>
      </div>
    </section>

    <!-- 治理边界 -->
    <section class="dash-notes">
      <article><i class="tone-ok">✓</i><div><b>安全参考路径可执行</b><p>仅 fixture-local 的任务可以先预览冻结 Plan，再显式确认运行。</p></div></article>
      <article><i class="tone-warn">!</i><div><b>治理边界明确</b><p>CI、审批、Review、外部诊断未接入时不会被推断为已覆盖。</p></div></article>
    </section>
  </section>
</template>

<style scoped>
.dash { max-width: 1280px; }
.dash-hero {
  display: flex; align-items: flex-end; justify-content: space-between; gap: 32px;
  margin: 24px 0 20px; padding: 28px 30px;
  border: 1px solid var(--line); border-radius: 16px;
  background: linear-gradient(120deg, color-mix(in srgb, var(--blue) 7%, var(--panel)), var(--panel) 55%, color-mix(in srgb, var(--violet) 5%, var(--panel)));
  box-shadow: var(--shadow);
}
.dash-hero h1 { margin: 0; font-size: 30px; letter-spacing: -.04em; }
.dash-hero .lede { margin: 10px 0 0; max-width: 520px; color: var(--muted); font-size: 13px; }
.dash-hero-actions { display: flex; gap: 10px; margin-top: 20px; }
.ghost-button {
  display: inline-flex; align-items: center; padding: 10px 14px;
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--panel); color: var(--ink); font-size: 13px; font-weight: 600;
}
.ghost-button:hover { border-color: var(--brand); color: var(--brand); }
.dash-hero-stats {
  display: grid; grid-template-columns: repeat(4, minmax(86px, 1fr)); gap: 10px;
  flex: 0 0 auto; min-width: 380px;
}
.dash-hero-stats .stat {
  padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px;
  background: color-mix(in srgb, var(--panel) 82%, transparent); text-align: center;
}
.dash-hero-stats .stat b { display: block; font-size: 22px; letter-spacing: -.03em; }
.dash-hero-stats .stat span { color: var(--soft); font-size: 11px; }

.dash-metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.dash-metric {
  display: flex; align-items: center; gap: 12px; padding: 15px 16px;
  border: 1px solid var(--line); border-radius: 12px; background: var(--panel);
  box-shadow: var(--shadow); transition: transform .12s ease, box-shadow .12s ease;
}
.dash-metric:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(27,31,35,.09); }
.dash-metric-icon {
  display: grid; place-items: center; width: 36px; height: 36px; flex: 0 0 36px;
  border-radius: 9px; font-size: 15px;
}
.dash-metric-icon svg { width: 18px; height: 18px; }
.dash-metric-body span { display: block; color: var(--soft); font-size: 11px; }
.dash-metric-body b { display: block; margin-top: 1px; font-size: 24px; letter-spacing: -.04em; line-height: 1.1; }

.tone-ok .dash-metric-icon { background: color-mix(in srgb, var(--mint) 13%, transparent); color: var(--mint); }
.tone-ok .dash-metric-body b { color: var(--mint); }
.tone-bad .dash-metric-icon { background: color-mix(in srgb, var(--red) 13%, transparent); color: var(--red); }
.tone-bad .dash-metric-body b { color: var(--red); }
.tone-warn .dash-metric-icon { background: color-mix(in srgb, var(--amber) 13%, transparent); color: var(--amber); }
.tone-warn .dash-metric-body b { color: var(--amber); }
.tone-muted .dash-metric-icon { background: var(--panel-2); color: var(--soft); }
.tone-muted .dash-metric-body b { color: var(--ink); }

.dash-panel { padding: 20px 22px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); box-shadow: var(--shadow); }
.dash-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.dash-panel-head h2 { margin: 0; font-size: 15px; }
.dash-panel-head span { display: block; margin-top: 3px; color: var(--soft); font-size: 11px; }
.text-link { color: var(--blue); font-size: 12px; font-weight: 700; }
.text-link:hover { text-decoration: underline; }

.dash-run-list { margin-top: 4px; }
.dash-run {
  display: grid; grid-template-columns: 40px minmax(0, 1fr) auto 90px; align-items: center; gap: 14px;
  padding: 12px 10px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 12px;
}
.dash-run:first-child { border-top: 0; }
.dash-run:hover { background: var(--panel-2); border-radius: 10px; }
.dash-run-icon {
  display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px;
  background: color-mix(in srgb, var(--blue) 9%, transparent); color: var(--blue); font-size: 14px;
}
.dash-run-id b { display: block; color: var(--ink); font-size: 13px; }
.dash-run-id small { display: block; margin-top: 2px; color: var(--soft); font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
.dash-run-badges { display: flex; gap: 6px; }
.dash-run-events { color: var(--soft); text-align: right; font-size: 11px; }
.dash-loading { padding: 14px 0; color: var(--soft); font-size: 12px; }

.dash-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.dash-notes article { display: flex; gap: 12px; padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.dash-notes i { display: grid; place-items: center; width: 28px; height: 28px; flex: 0 0 28px; border-radius: 8px; font-style: normal; font-weight: 700; }
.dash-notes .tone-ok { background: color-mix(in srgb, var(--mint) 12%, transparent); color: var(--mint); }
.dash-notes .tone-warn { background: color-mix(in srgb, var(--amber) 12%, transparent); color: var(--amber); }
.dash-notes b { font-size: 12px; }
.dash-notes p { margin: 4px 0 0; color: var(--muted); font-size: 11px; }

@media (max-width: 1080px) {
  .dash-hero { flex-direction: column; align-items: stretch; }
  .dash-hero-stats { min-width: 0; grid-template-columns: repeat(4, 1fr); }
  .dash-metrics { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 700px) {
  .dash-hero-stats { grid-template-columns: repeat(2, 1fr); }
  .dash-metrics { grid-template-columns: repeat(2, 1fr); }
  .dash-run { grid-template-columns: 36px minmax(0, 1fr); }
  .dash-run-badges, .dash-run-events { display: none; }
  .dash-notes { grid-template-columns: 1fr; }
}
</style>
