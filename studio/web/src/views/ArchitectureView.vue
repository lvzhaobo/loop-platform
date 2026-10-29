<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ChecksResponse, LifecycleResponse, PipelineResponse, Profile, ProfileComposerCatalog, RunSummary } from '../api/contracts'
import StatusBadge from '../components/StatusBadge.vue'

// 架构与运行逻辑：一张含沙箱运行态的大图。
// 顶部运行态概览 → 五阶段架构流水线 → 运行逻辑（编译/多Agent/门禁/生成/开关）→ 生命周期漏斗 + 最近运行。

const catalog = ref<ProfileComposerCatalog | null>(null)
const profiles = ref<Profile[]>([])
const runs = ref<RunSummary[]>([])
const lifecycle = ref<LifecycleResponse | null>(null)
const pipeline = ref<PipelineResponse | null>(null)
const checks = ref<ChecksResponse | null>(null)
const error = ref('')
const loading = ref(true)

const STAGE_LABEL: Record<string, string> = { source: '需求来源', compiler: 'Spec 编译', maker: 'Maker 生成', checker: 'Checker 验收', delivery: '交付' }
const STAGE_ORDER = ['source', 'compiler', 'maker', 'checker', 'delivery'] as const

const stats = computed(() => {
  const total = runs.value.length
  const passed = runs.value.filter(r => r.status === 'passed').length
  const failed = runs.value.filter(r => r.status === 'failed').length
  return {
    total, failed,
    passRate: total ? Math.round((passed / total) * 100) : null,
    profiles: profiles.value.filter(p => p.valid).length,
    checks: checks.value?.summary?.total || 0,
  }
})

const stages = computed(() => STAGE_ORDER.map(key => ({ key, label: STAGE_LABEL[key], items: catalog.value?.stages[key] || [] })))

// 生命周期：每阶段通过率
const lifecycleStages = computed(() => {
  const byKey: Record<string, { passed: number; failed: number; total: number }> = {}
  for (const s of lifecycle.value?.stages || []) {
    byKey[s.stage] = { passed: s.status_counts.passed || 0, failed: s.status_counts.failed || 0, total: s.run_count }
  }
  return STAGE_ORDER.map(key => ({ key, label: STAGE_LABEL[key], ...(byKey[key] || { passed: 0, failed: 0, total: 0 }) }))
})

onMounted(async () => {
  loading.value = true; error.value = ''
  try {
    const [c, p, r, l, pl, ch] = await Promise.all([api.profileComposerCatalog(), api.profiles(), api.runs(), api.lifecycle(), api.pipeline(), api.checks()])
    catalog.value = c.catalog; profiles.value = p.profiles; runs.value = r.runs; lifecycle.value = l; pipeline.value = pl; checks.value = ch
  } catch (e) { error.value = e instanceof Error ? e.message : '无法读取架构与运行数据' }
  finally { loading.value = false }
})
</script>

<template>
  <section class="page arch">
    <div class="page-heading">
      <div>
        <p class="eyebrow">ARCHITECTURE &amp; RUNTIME</p>
        <h1>架构与运行逻辑</h1>
        <p>Loop Platform 沙箱的全景：需求来源 → Spec 编译 → 生成 → 验收 → 交付，叠加实时运行态。</p>
      </div>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取架构与运行数据…</p>

    <template v-else>
      <!-- 运行态概览 -->
      <div class="arch-stats">
        <div class="arch-stat"><b>{{ stats.total }}</b><span>运行总数</span></div>
        <div class="arch-stat"><b>{{ stats.passRate === null ? '—' : stats.passRate + '%' }}</b><span>通过率</span></div>
        <div class="arch-stat"><b>{{ stats.failed }}</b><span>失败</span></div>
        <div class="arch-stat"><b>{{ stats.profiles }}</b><span>有效 Profile</span></div>
        <div class="arch-stat"><b>{{ stats.checks }}</b><span>约束项</span></div>
      </div>

      <!-- 架构流水线 -->
      <section class="arch-panel">
        <h2>架构流水线</h2>
        <div class="arch-flow">
          <template v-for="(s, i) in stages" :key="s.key">
            <div class="arch-stage">
              <div class="arch-stage-head"><span class="arch-stage-no">{{ i + 1 }}</span><b>{{ s.label }}</b></div>
              <div class="arch-comps">
                <span v-for="c in s.items" :key="c.id" class="arch-comp" :class="{ planned: c.available === false }">{{ c.label }}</span>
              </div>
            </div>
            <span v-if="i < stages.length - 1" class="arch-arrow">→</span>
          </template>
        </div>
      </section>

      <!-- 运行逻辑 -->
      <section class="arch-panel">
        <h2>运行逻辑</h2>
        <div class="logic-grid">
          <article v-for="st in pipeline?.stages || []" :key="st.key" class="logic-card">
            <div class="logic-head"><b>{{ st.name }}</b><small>{{ st.items.length }} 项</small></div>
            <p>{{ st.desc }}</p>
            <ul class="logic-items">
              <li v-for="it in st.items" :key="it.id">
                <span>{{ it.name }}</span>
                <em v-if="it.desc" class="logic-desc">{{ it.desc }}</em>
                <i v-if="it.on !== undefined" class="logic-on" :class="{ off: !it.on }">{{ it.on ? '开' : '关' }}</i>
              </li>
            </ul>
          </article>
        </div>
      </section>

      <!-- 沙箱运行态：生命周期漏斗 + 最近运行 -->
      <div class="arch-two-col">
        <section class="arch-panel">
          <h2>生命周期漏斗</h2>
          <div class="funnel">
            <div v-for="s in lifecycleStages" :key="s.key" class="funnel-row">
              <span class="funnel-label">{{ s.label }}</span>
              <div class="funnel-bar"><div class="funnel-fill pass" :style="{ width: s.total ? (s.passed / s.total * 100) + '%' : '0%' }"></div><div class="funnel-fill fail" :style="{ width: s.total ? (s.failed / s.total * 100) + '%' : '0%' }"></div></div>
              <span class="funnel-num">{{ s.passed }}/{{ s.total }}</span>
            </div>
          </div>
        </section>

        <section class="arch-panel">
          <h2>最近运行</h2>
          <p v-if="!runs.length" class="empty-state">暂无运行记录。</p>
          <div v-else class="recent-runs">
            <RouterLink v-for="run in runs.slice(0, 6)" :key="run.run_id" :to="`/runs/${run.run_id}`" class="recent-run">
              <div class="recent-run-main"><b>{{ run.task?.title || run.run_id }}</b><small>{{ run.run_id }}</small></div>
              <div class="stage-dots"><span v-for="k in STAGE_ORDER" :key="k" class="stage-dot" :class="run.stage_statuses?.[k] || 'muted'" :title="STAGE_LABEL[k] + ': ' + (run.stage_statuses?.[k] || '未到')"></span></div>
              <StatusBadge :status="run.status" />
            </RouterLink>
          </div>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.arch-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 11px; margin-bottom: 16px; }
.arch-stat { padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); box-shadow: var(--shadow); }
.arch-stat b { display: block; font-size: 24px; letter-spacing: -.03em; }
.arch-stat span { color: var(--soft); font-size: 11px; }
.arch-panel { margin-top: 14px; padding: 18px 20px; border: 1px solid var(--line); border-radius: 13px; background: var(--panel); }
.arch-panel h2 { margin: 0 0 14px; font-size: 15px; }

.arch-flow { display: flex; align-items: stretch; gap: 8px; }
.arch-stage { flex: 1; padding: 13px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); }
.arch-stage-head { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; }
.arch-stage-no { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 6px; background: var(--brand); color: #fff; font-size: 11px; font-weight: 700; }
.arch-stage-head b { font-size: 13px; }
.arch-comps { display: flex; flex-wrap: wrap; gap: 6px; }
.arch-comp { padding: 3px 8px; border-radius: 6px; background: var(--panel); border: 1px solid var(--line); color: var(--muted); font-size: 11px; }
.arch-comp.planned { background: color-mix(in srgb, var(--amber) 10%, transparent); color: var(--amber); border-style: dashed; }
.arch-arrow { align-self: center; color: var(--soft); font-size: 16px; }

.logic-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 11px; }
.logic-card { padding: 14px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); }
.logic-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.logic-head b { font-size: 13px; }
.logic-head small { color: var(--soft); font-size: 11px; }
.logic-card p { margin: 6px 0 8px; color: var(--soft); font-size: 11px; }
.logic-items { margin: 0; padding: 0; list-style: none; }
.logic-items li { display: flex; align-items: baseline; gap: 8px; padding: 5px 0; border-top: 1px solid var(--line-soft); font-size: 12px; }
.logic-items li span { font-weight: 600; }
.logic-desc { color: var(--soft); font-size: 11px; font-style: normal; }
.logic-on { margin-left: auto; padding: 1px 7px; border-radius: 5px; background: color-mix(in srgb, var(--mint) 13%, transparent); color: var(--mint); font-style: normal; font-size: 10px; }
.logic-on.off { background: var(--panel-2); color: var(--soft); }

.arch-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.funnel { display: flex; flex-direction: column; gap: 10px; }
.funnel-row { display: grid; grid-template-columns: 72px 1fr 42px; align-items: center; gap: 10px; }
.funnel-label { color: var(--muted); font-size: 12px; }
.funnel-bar { display: flex; height: 14px; border-radius: 7px; background: var(--panel-2); overflow: hidden; }
.funnel-fill { height: 100%; }
.funnel-fill.pass { background: color-mix(in srgb, var(--mint) 65%, transparent); }
.funnel-fill.fail { background: color-mix(in srgb, var(--red) 65%, transparent); }
.funnel-num { color: var(--soft); font-size: 11px; text-align: right; }
.recent-runs { display: flex; flex-direction: column; }
.recent-run { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--line-soft); }
.recent-run:hover { background: var(--panel-2); }
.recent-run-main b { display: block; font-size: 12px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-run-main small { color: var(--soft); font-size: 10px; font-family: ui-monospace, Menlo, monospace; }
.stage-dots { display: flex; gap: 4px; }
.stage-dot { width: 9px; height: 9px; border-radius: 50%; }
.stage-dot.passed { background: var(--mint); }
.stage-dot.failed { background: var(--red); }
.stage-dot.muted { background: var(--line); }
@media (max-width: 1080px) { .arch-flow { flex-wrap: wrap; } .arch-stage { min-width: 140px; } .arch-arrow { display: none; } }
@media (max-width: 760px) { .arch-stats { grid-template-columns: repeat(3, 1fr); } .logic-grid, .arch-two-col { grid-template-columns: 1fr; } }
</style>
