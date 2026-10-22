<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ComponentDescriptor, ComposerStage, LifecycleResponse, Profile, ProfileComposerCatalog, StageCoverage } from '../api/contracts'

// 只读全景图：把 source → compiler → maker → checker → delivery 五段流水线画成一张画布，
// 同时叠加真实运行漏斗（lifecycle）与组件目录（catalog）。选中一个 Profile 会高亮它在每段
// 实际选用的组件路径。本视图不写入、不执行、不联网（除读取只读投影接口外）。

const stages: Array<{ id: ComposerStage; num: number; label: string; hint: string }> = [
  { id: 'source', num: 1, label: 'Source', hint: '需求来源' },
  { id: 'compiler', num: 2, label: 'Compiler', hint: '需求转 Spec' },
  { id: 'maker', num: 3, label: 'Maker', hint: '代码生成' },
  { id: 'checker', num: 4, label: 'Checkers', hint: '质量闸口' },
  { id: 'delivery', num: 5, label: 'Delivery', hint: '制品去向' },
]

const catalog = ref<ProfileComposerCatalog | null>(null)
const coverage = ref<Record<string, StageCoverage>>({})
const profiles = ref<Profile[]>([])
const activeId = ref('')
const error = ref('')
const loading = ref(true)

const activeProfile = computed(() => profiles.value.find(p => p.id === activeId.value) || null)

const variants = (name: ComposerStage): ComponentDescriptor[] => catalog.value?.stages[name] || []

// 当前 Profile 在该段选用的组件 id 集合（checker 可多个）
function pathIds(name: ComposerStage): string[] {
  const p = activeProfile.value
  if (!p) return []
  if (name === 'source') return [typeof p.source === 'string' ? p.source : '']
  if (name === 'checker') return p.checkers || []
  return [(p as Record<string, unknown>)[name] as string].filter(Boolean)
}
const onPath = (name: ComposerStage, id: string) => pathIds(name).includes(id)

// 每个组件被多少 Profile 采用（反映真实使用面）
const usage = computed(() => {
  const map: Record<string, number> = {}
  for (const p of profiles.value) {
    const src = typeof p.source === 'string' ? p.source : ''
    const bump = (name: string, id?: string) => { if (id) map[`${name}:${id}`] = (map[`${name}:${id}`] || 0) + 1 }
    bump('source', src); bump('compiler', p.compiler); bump('maker', p.maker); bump('delivery', p.delivery)
    for (const c of p.checkers || []) bump('checker', c)
  }
  return map
})
const usageOf = (name: string, id: string) => usage.value[`${name}:${id}`] || 0

const CAP_SHORT: Record<string, string> = { network: '网', model: '模', git: 'Git', publish: '发布', deploy: '部署', ssh: 'SSH' }
const capsOf = (item: ComponentDescriptor) => Object.entries(item.capabilities).filter(([, on]) => on).map(([k]) => CAP_SHORT[k] || k)

function funnel(name: ComposerStage) {
  const c = coverage.value[name]
  const total = c?.run_count || 0
  const s = c?.status_counts
  const seg = [
    { key: 'passed', n: s?.passed || 0, cls: 'ok' },
    { key: 'failed', n: s?.failed || 0, cls: 'bad' },
    { key: 'skipped', n: s?.skipped || 0, cls: 'skip' },
    { key: 'unavailable', n: s?.unavailable || 0, cls: 'na' },
    { key: 'indeterminate', n: s?.indeterminate || 0, cls: 'ind' },
    { key: 'not_reached', n: c?.not_reached_runs || 0, cls: 'nr' },
  ].filter(x => x.n > 0)
  return { total, recorded: c?.recorded_runs || 0, passed: s?.passed || 0, failed: s?.failed || 0, notReached: c?.not_reached_runs || 0, seg }
}
const pct = (n: number, total: number) => (total ? (n / total) * 100 : 0)

const totals = computed(() => {
  const src = funnel('source'), del = funnel('delivery')
  return { runs: src.total, delivered: del.passed, endFailed: del.failed }
})

onMounted(async () => {
  try {
    const [cat, life, prof] = await Promise.all([api.profileComposerCatalog(), api.lifecycle(), api.profiles()])
    catalog.value = cat.catalog
    const map: Record<string, StageCoverage> = {}
    for (const s of (life as LifecycleResponse).stages || []) map[s.stage] = s
    coverage.value = map
    profiles.value = prof.profiles.filter(p => p.valid !== false)
    const eligible = profiles.value.find(p => p.execution_eligible) || profiles.value[0]
    activeId.value = eligible?.id || ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : '无法读取全景图数据'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page panorama">
    <div class="page-heading">
      <div>
        <p class="eyebrow">FIVE-STAGE PIPELINE · LIVE FUNNEL</p>
        <h1>交付全景图</h1>
        <p>把 source → compiler → maker → checker → delivery 五段链路的组件目录与真实运行漏斗画在一张画布上；选中 Profile 即高亮它的落地路径。只读视图，不执行、不写入。</p>
      </div>
      <label class="profile-pick">
        <span>追踪 Profile</span>
        <select v-model="activeId">
          <option value="">不追踪（看全量目录）</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.id }} · v{{ p.version }}</option>
        </select>
      </label>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取组件目录、运行漏斗与 Profile 库…</p>

    <template v-else-if="catalog">
      <section class="pano-summary">
        <div><b>{{ totals.runs }}</b><span>进入流程的 Run</span></div>
        <i>→</i>
        <div><b class="ok">{{ totals.delivered }}</b><span>走完 Delivery 通过</span></div>
        <i>→</i>
        <div><b class="bad">{{ totals.endFailed }}</b><span>末段失败</span></div>
        <div class="legend">
          <em class="ok">通过</em><em class="bad">失败</em><em class="skip">跳过</em><em class="na">不可用</em><em class="ind">不确定</em><em class="nr">未到达</em>
        </div>
      </section>

      <section class="pano-flow">
        <template v-for="(st, i) in stages" :key="st.id">
          <article class="pano-stage">
            <header>
              <span class="num">{{ st.num }}</span>
              <div><b>{{ st.label }}</b><small>{{ st.hint }}</small></div>
            </header>

            <div class="funnel">
              <div class="bar">
                <i v-for="seg in funnel(st.id).seg" :key="seg.key" :class="seg.cls" :style="{ width: pct(seg.n, funnel(st.id).total) + '%' }" :title="`${seg.key}: ${seg.n}`"></i>
              </div>
              <div class="funnel-meta">
                <span>{{ funnel(st.id).recorded }}/{{ funnel(st.id).total }} 有记录</span>
                <span class="ok">{{ funnel(st.id).passed }} 通过</span>
                <span v-if="funnel(st.id).failed" class="bad">{{ funnel(st.id).failed }} 失败</span>
                <span v-if="funnel(st.id).notReached" class="nr">未到达 {{ funnel(st.id).notReached }}</span>
              </div>
            </div>

            <ul class="nodes">
              <li v-for="item in variants(st.id)" :key="item.id" class="node" :class="{ on: onPath(st.id, item.id), exp: item.experimental }">
                <div class="node-top">
                  <b>{{ item.label }}</b>
                  <span v-if="usageOf(st.id, item.id)" class="usage">{{ usageOf(st.id, item.id) }} Profile</span>
                </div>
                <div class="node-tags">
                  <span v-if="item.experimental" class="tag exp-tag">实验性</span>
                  <span v-for="c in capsOf(item)" :key="c" class="tag cap">{{ c }}</span>
                  <span v-if="!capsOf(item).length" class="tag local">离线本地</span>
                  <span v-if="onPath(st.id, item.id)" class="tag on-tag">链路中</span>
                </div>
              </li>
              <li v-if="!variants(st.id).length" class="node empty">该段无已注册组件</li>
            </ul>
          </article>
          <i v-if="i < stages.length - 1" class="pano-arrow" aria-hidden="true">→</i>
        </template>
      </section>

      <section v-if="activeProfile" class="pano-path workspace-panel">
        <div class="panel-heading"><div><h2>{{ activeProfile.id }} 的落地路径</h2><span>{{ activeProfile.description || '无说明' }}</span></div>
          <span class="elig" :class="activeProfile.execution_eligible ? 'ok' : 'bad'">{{ activeProfile.execution_eligible ? '可执行' : '暂不可执行' }}</span>
        </div>
        <ol class="path-steps">
          <li v-for="st in stages" :key="st.id"><b>{{ st.label }}</b><span>{{ pathIds(st.id).map(id => variants(st.id).find(v => v.id === id)?.label || id).join(' + ') || '—' }}</span></li>
        </ol>
        <p v-if="activeProfile.execution_blocker" class="data-warning">阻塞：{{ activeProfile.execution_blocker }}</p>
      </section>

      <p class="pano-note">数据口径：漏斗来自 <code>/api/observability/lifecycle</code>（已验证事件投影），组件目录来自 <code>/api/profile-composer/catalog</code>（服务端白名单）。“未到达”表示上游失败导致该段没被执行，不等于该段失败。</p>
    </template>
  </section>
</template>

<style scoped>
.profile-pick { display: grid; gap: 5px; min-width: 220px; color: var(--muted); font-size: 11px }
.profile-pick select { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); padding: 9px; color: var(--ink) }

.pano-summary { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin: 6px 0 18px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel) }
.pano-summary > div { display: grid; gap: 2px }
.pano-summary b { font-size: 22px; font-weight: 700; line-height: 1 }
.pano-summary b.ok { color: var(--mint) }
.pano-summary b.bad { color: var(--red) }
.pano-summary span { color: var(--soft); font-size: 11px }
.pano-summary i { color: var(--blue); font-style: normal; font-size: 18px }
.pano-summary .legend { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto }
.pano-summary .legend em { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); font-size: 10px; font-style: normal }
.pano-summary .legend em::before { content: ''; width: 9px; height: 9px; border-radius: 2px; background: currentColor }
.legend .ok { color: var(--mint) } .legend .bad { color: var(--red) } .legend .skip { color: var(--amber) }
.legend .na { color: var(--soft) } .legend .ind { color: var(--violet) } .legend .nr { color: var(--line) }

.pano-flow { display: flex; align-items: stretch; gap: 6px; overflow-x: auto; padding-bottom: 8px }
.pano-stage { flex: 1 0 210px; min-width: 210px; display: grid; align-content: start; gap: 12px; padding: 14px; border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--panel) 88%, transparent) }
.pano-stage > header { display: flex; align-items: center; gap: 9px }
.pano-stage .num { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; background: var(--ink); color: var(--bg); font-size: 12px; font-weight: 700 }
.pano-stage header b, .pano-stage header small { display: block }
.pano-stage header b { font-size: 13px }
.pano-stage header small { color: var(--soft); font-size: 10px }
.pano-arrow { align-self: center; flex: 0 0 auto; color: var(--blue); font-style: normal; font-size: 16px }

.funnel { display: grid; gap: 6px }
.funnel .bar { display: flex; height: 8px; border-radius: 5px; overflow: hidden; background: var(--line-soft) }
.funnel .bar i { height: 100% }
.funnel .bar .ok { background: var(--mint) } .funnel .bar .bad { background: var(--red) } .funnel .bar .skip { background: var(--amber) }
.funnel .bar .na { background: var(--soft) } .funnel .bar .ind { background: var(--violet) } .funnel .bar .nr { background: var(--line) }
.funnel-meta { display: flex; flex-wrap: wrap; gap: 8px; color: var(--soft); font-size: 10px }
.funnel-meta .ok { color: var(--mint) } .funnel-meta .bad { color: var(--red) } .funnel-meta .nr { color: var(--soft) }

.nodes { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none }
.node { padding: 8px 9px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2) }
.node.on { border-color: color-mix(in srgb, var(--brand) 55%, var(--line)); background: color-mix(in srgb, var(--brand) 10%, var(--panel)) }
.node.exp { border-style: dashed }
.node.empty { color: var(--soft); font-size: 11px; text-align: center; border-style: dashed }
.node-top { display: flex; align-items: baseline; justify-content: space-between; gap: 6px }
.node-top b { font-size: 12px; font-weight: 600 }
.node-top .usage { color: var(--soft); font-size: 9px; white-space: nowrap }
.node-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px }
.node-tags .tag { padding: 1px 5px; border-radius: 4px; background: color-mix(in srgb, var(--ink) 6%, transparent); color: var(--muted); font-size: 9px }
.node-tags .cap { background: color-mix(in srgb, var(--amber) 16%, transparent); color: var(--amber) }
.node-tags .local { background: color-mix(in srgb, var(--mint) 14%, transparent); color: var(--mint) }
.node-tags .exp-tag { background: color-mix(in srgb, var(--violet) 16%, transparent); color: var(--violet) }
.node-tags .on-tag { background: var(--brand); color: #fff }

.pano-path { margin-top: 18px }
.pano-path .elig { padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600 }
.pano-path .elig.ok { background: color-mix(in srgb, var(--mint) 14%, transparent); color: var(--mint) }
.pano-path .elig.bad { background: color-mix(in srgb, var(--red) 14%, transparent); color: var(--red) }
.path-steps { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 0; padding: 0; list-style: none }
.path-steps li { flex: 1 1 160px; display: grid; gap: 3px; padding: 10px 12px; border-left: 2px solid var(--brand); border-radius: 0 8px 8px 0; background: var(--panel-2) }
.path-steps b { font-size: 11px; color: var(--soft) }
.path-steps span { font-size: 13px; font-weight: 600 }

.pano-note { margin-top: 16px; color: var(--soft); font-size: 11px; line-height: 1.6 }
.pano-note code { padding: 1px 5px; border-radius: 4px; background: var(--code-bg); color: var(--code-ink); font-size: 11px }

@media (max-width: 900px) {
  .pano-flow { flex-wrap: nowrap }
  .pano-summary .legend { margin-left: 0; flex-basis: 100% }
}
</style>
