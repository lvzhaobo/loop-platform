<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ComponentDescriptor, ComposerStage, Profile, ProfileComposerCatalog } from '../api/contracts'

// 流水线拓扑画布：把五段链路的「可插拔组件 + 连线 + 回退/门禁条件」画成一张有向图。
// 边与条件全部来自代码事实（engine/core/run_executor.py），不是示意：
//   前向 pass 判据 237-277；失败即终止 _failed 241-277；重试仅 retry_delivery 118-137；
//   替换约束 validate_executable 172-205。代码里没有自动 rollback，这里也不画。

type Cand = ComponentDescriptor & { x: number; y: number; on: boolean; executable: boolean }
type Slot = { stage: ComposerStage; num: number; label: string; hint: string; x: number; y: number; w: number; h: number; cands: Cand[] }
type Edge = { key: string; kind: 'fwd' | 'fail' | 'retry' | 'gate'; d: string; lx: number; ly: number; label: string }

// 可执行子集（run_executor.validate_executable 白名单）
const EXECUTABLE: Record<ComposerStage, string[]> = {
  source: ['local_queue'],
  compiler: ['simple', 'mumuspec'],
  maker: ['sample', 'deepseek'],
  checker: ['security', 'runtime', 'e2e', 'pages'],
  delivery: ['local_artifact', 'github_workflow'],
}
const STAGES: Array<{ id: ComposerStage; num: number; label: string; hint: string; pass: string; fail: string }> = [
  { id: 'source', num: 1, label: 'Source', hint: '需求来源', pass: '快照写入 → 进入编译', fail: '（快照恒通过）' },
  { id: 'compiler', num: 2, label: 'Compiler', hint: '需求转 Spec', pass: 'spec.validate() 三件套通过', fail: '校验失败/异常 → Run=failed' },
  { id: 'maker', num: 3, label: 'Maker', hint: '代码生成', pass: '返回 artifact.digest', fail: '异常/无 digest → Run=failed' },
  { id: 'checker', num: 4, label: 'Checkers', hint: '质量闸口', pass: '全部 status=passed', fail: 'status≠passed → 挡住 Delivery' },
  { id: 'delivery', num: 5, label: 'Delivery', hint: '制品去向', pass: 'result.status=passed → done', fail: '异常/非 passed → Run=failed' },
]

// 布局常量（px）
const PAD = 20, COLW = 178, COLGAP = 92, SLOT_TOP = 96
const NODE_H = 42, NODE_GAP = 8, SLOT_HDR = 30, SLOT_PAD = 12, CHAIN_Y = SLOT_TOP + SLOT_PAD + SLOT_HDR + NODE_H / 2

const catalog = ref<ProfileComposerCatalog | null>(null)
const profiles = ref<Profile[]>([])
const activeId = ref('')
const error = ref('')
const loading = ref(true)

const activeProfile = computed(() => profiles.value.find(p => p.id === activeId.value) || null)

function chosen(stage: ComposerStage): string[] {
  const p = activeProfile.value
  if (!p) return []
  if (stage === 'source') return [typeof p.source === 'string' ? p.source : '']
  if (stage === 'checker') return p.checkers || []
  return [(p as unknown as Record<string, string>)[stage]].filter(Boolean)
}

const CAP_SHORT: Record<string, string> = { network: '网', model: '模', git: 'Git', publish: '发布', deploy: '部署', ssh: 'SSH' }
const capsOf = (c: ComponentDescriptor) => Object.entries(c.capabilities).filter(([, on]) => on).map(([k]) => CAP_SHORT[k] || k)

const graph = computed(() => {
  const cat = catalog.value
  if (!cat) return { slots: [] as Slot[], edges: [] as Edge[], width: 0, height: 0, failY: 0 }
  const slots: Slot[] = STAGES.map((st, i) => {
    const list = cat.stages[st.id] || []
    const on = chosen(st.id)
    const h = SLOT_PAD * 2 + SLOT_HDR + list.length * NODE_H + Math.max(0, list.length - 1) * NODE_GAP
    const x = PAD + i * (COLW + COLGAP)
    const cands: Cand[] = list.map((c, k) => ({
      ...c,
      x: x + SLOT_PAD,
      y: SLOT_TOP + SLOT_PAD + SLOT_HDR + k * (NODE_H + NODE_GAP),
      on: on.includes(c.id),
      executable: EXECUTABLE[st.id].includes(c.id),
    }))
    return { stage: st.id, num: st.num, label: st.label, hint: st.hint, x, y: SLOT_TOP, w: COLW, h, cands }
  })
  const maxH = Math.max(...slots.map(s => s.h))
  const failY = SLOT_TOP + maxH + 84
  const edges: Edge[] = []
  // 前向成功链（水平）
  for (let i = 0; i < slots.length - 1; i++) {
    const a = slots[i], b = slots[i + 1]
    const x1 = a.x + a.w, x2 = b.x, mid = (x1 + x2) / 2
    edges.push({ key: `fwd-${i}`, kind: 'fwd', d: `M ${x1} ${CHAIN_Y} H ${x2 - 8}`, lx: mid, ly: CHAIN_Y - 12, label: STAGES[i + 1].pass })
  }
  // 门禁边（checker → delivery 特别标注）
  const ck = slots[3], dl = slots[4]
  edges.push({ key: 'gate', kind: 'gate', d: `M ${ck.x + ck.w} ${CHAIN_Y + 22} H ${dl.x - 8}`, lx: (ck.x + ck.w + dl.x) / 2, ly: CHAIN_Y + 34, label: '仅 passed 才放行' })
  // 失败终止边（每段 → 底部终止条）
  slots.forEach((s, i) => {
    if (i === 0) return
    const cx = s.x + s.w / 2
    edges.push({ key: `fail-${i}`, kind: 'fail', d: `M ${cx} ${s.y + s.h} V ${failY - 8}`, lx: cx, ly: (s.y + s.h + failY) / 2, label: STAGES[i].fail })
  })
  // 重试回退环（delivery → delivery）
  const dx = dl.x + dl.w / 2, dy = dl.y + dl.h
  edges.push({ key: 'retry', kind: 'retry', d: `M ${dx + 40} ${dy} C ${dx + 40} ${dy + 46}, ${dx - 40} ${dy + 46}, ${dx - 40} ${dy}`, lx: dx, ly: dy + 40, label: 'retry_delivery：仅重投失败交付' })
  const width = PAD * 2 + slots.length * COLW + (slots.length - 1) * COLGAP
  const height = failY + 128
  return { slots, edges, width, height, failY }
})

const edgeColor: Record<Edge['kind'], string> = { fwd: 'var(--mint)', fail: 'var(--red)', retry: 'var(--amber)', gate: 'var(--blue)' }

// 替换约束（validate_executable 的真实组合规则）
const REPLACE_RULES = [
  'delivery=github_workflow ⇒ 强制 maker=deepseek 且 checkers⊇{security,e2e}，且禁 SSH。',
  'delivery=local_artifact + maker=sample ⇒ 禁止一切外部权限（离线安全基线）。',
  'delivery=local_artifact + maker=deepseek ⇒ 仅允许 网络+模型，禁 Git/SSH/发布/部署。',
  'profile=fixture-local ⇒ 锁定 simple+sample+security+local_artifact，权限全禁。',
  'checker=process 已注册但不在可执行子集 {security,runtime,e2e,pages}，Run 路径用不到。',
  'compiler=mumuspec 为实验性，当前回退 SimpleCompiler（provenance=mumuspec-fallback）。',
]
const ROLLBACK_NOTES = [
  '代码中没有自动 rollback：任一段失败即 _failed 终止，Delivery 不执行，冻结 Plan 与制品不被覆盖。',
  '唯一的回退式动作是 retry_delivery：复用已冻结 Plan 与制品，只重投失败的 Delivery，不重跑模型/Checker。',
  'policy.on_unavailable（block/review_required/continue）是草稿声明字段，run_executor 当前未据此分支执行。',
]

onMounted(async () => {
  try {
    const [cat, prof] = await Promise.all([api.profileComposerCatalog(), api.profiles()])
    catalog.value = cat.catalog
    profiles.value = prof.profiles.filter(p => p.valid !== false)
    activeId.value = (profiles.value.find(p => p.execution_eligible) || profiles.value[0])?.id || ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : '无法读取组件目录与 Profile 库'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page pipe-graph">
    <div class="page-heading">
      <div>
        <p class="eyebrow">TOPOLOGY · EDGES · ROLLBACK CONDITIONS</p>
        <h1>流水线拓扑画布</h1>
        <p>五段链路的有向图：每段列出可插拔/可替换的组件候选，连线标出前向判据、门禁阻断与失败终止，delivery 上画出唯一的回退式动作 retry_delivery。边与条件取自 <code>run_executor.py</code>，非示意。</p>
      </div>
      <label class="pick">
        <span>追踪 Profile</span>
        <select v-model="activeId">
          <option value="">不追踪（看全部候选）</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.id }} · v{{ p.version }}</option>
        </select>
      </label>
    </div>

    <p v-if="error" class="data-warning">⚠ {{ error }}</p>
    <p v-if="loading" class="empty-state">正在读取组件目录与 Profile 库…</p>

    <template v-else-if="catalog">
      <div class="legend">
        <em class="fwd">前向判据</em><em class="gate">门禁阻断</em><em class="fail">失败终止</em><em class="retry">回退重试</em>
        <em class="on">链路中</em><em class="alt">可替换候选</em><em class="na">不可执行</em>
      </div>

      <div class="graph-scroll">
        <div class="graph-canvas" :style="{ width: graph.width + 'px', height: graph.height + 'px' }">
          <svg class="edges" :width="graph.width" :height="graph.height">
            <defs>
              <marker id="pg-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill="context-stroke" />
              </marker>
            </defs>
            <path v-for="e in graph.edges" :key="e.key" :d="e.d" class="edge" :class="e.kind" :style="{ stroke: edgeColor[e.kind] }" marker-end="url(#pg-arrow)" />
          </svg>

          <!-- 失败终止条 -->
          <div class="fail-bar" :style="{ left: PAD + 'px', top: graph.failY + 'px', width: (graph.width - PAD * 2) + 'px' }">
            Run 终止 · failed / unavailable（Delivery 未执行；冻结 Plan 与制品不被覆盖）
          </div>

          <!-- 边标签 -->
          <div v-for="e in graph.edges" :key="'l-' + e.key" class="edge-label" :class="e.kind" :style="{ left: e.lx + 'px', top: e.ly + 'px' }">{{ e.label }}</div>

          <!-- 组件槽位 -->
          <div v-for="s in graph.slots" :key="s.stage" class="slot" :style="{ left: s.x + 'px', top: s.y + 'px', width: s.w + 'px', height: s.h + 'px' }">
            <div class="slot-head"><span class="num">{{ s.num }}</span><div><b>{{ s.label }}</b><small>{{ s.hint }}</small></div></div>
            <div
              v-for="c in s.cands" :key="c.id" class="cand"
              :class="{ on: c.on, alt: !c.on, na: !c.executable }"
              :style="{ left: (c.x - s.x) + 'px', top: (c.y - s.y) + 'px', width: (s.w - 2 * SLOT_PAD) + 'px' }"
              :title="c.description"
            >
              <div class="cand-top">
                <b>{{ c.label }}</b>
                <span v-if="c.on" class="pill on">链路中</span>
                <span v-else-if="!c.executable" class="pill na">不可执行</span>
                <span v-else class="pill alt">可替换</span>
              </div>
              <div class="cand-tags">
                <span v-if="c.experimental" class="tag exp">实验性</span>
                <span v-for="cap in capsOf(c)" :key="cap" class="tag cap">{{ cap }}</span>
                <span v-if="!capsOf(c).length" class="tag local">离线本地</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <section class="panels">
        <article class="workspace-panel">
          <div class="panel-heading"><div><h2>回退与重试条件</h2><span>代码里唯一的回退式动作</span></div></div>
          <ul class="rule-list rollback"><li v-for="t in ROLLBACK_NOTES" :key="t">{{ t }}</li></ul>
        </article>
        <article class="workspace-panel">
          <div class="panel-heading"><div><h2>可插拔 / 替换约束</h2><span>来自 validate_executable</span></div></div>
          <ul class="rule-list"><li v-for="t in REPLACE_RULES" :key="t">{{ t }}</li></ul>
        </article>
      </section>
    </template>
  </section>
</template>

<style scoped>
.pick { display: grid; gap: 5px; min-width: 220px; color: var(--muted); font-size: 11px }
.pick select { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); padding: 9px; color: var(--ink) }
.page-heading code, .rule-list code { padding: 1px 5px; border-radius: 4px; background: var(--code-bg); color: var(--code-ink); font-size: 11px }

.legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 4px 0 14px; color: var(--muted); font-size: 11px }
.legend em { display: inline-flex; align-items: center; gap: 5px; font-style: normal }
.legend em::before { content: ''; width: 14px; height: 0; border-top: 2px solid currentColor }
.legend .on::before, .legend .alt::before, .legend .na::before { width: 11px; height: 11px; border: 1.5px solid currentColor; border-top-width: 1.5px }
.legend .fwd { color: var(--mint) } .legend .gate { color: var(--blue) } .legend .fail { color: var(--red) } .legend .retry { color: var(--amber) }
.legend .on { color: var(--brand) } .legend .alt { color: var(--soft) } .legend .na { color: var(--red) }

.graph-scroll { overflow-x: auto; padding-bottom: 8px }
.graph-canvas { position: relative }
.edges { position: absolute; inset: 0; pointer-events: none; overflow: visible }
.edge { fill: none; stroke-width: 1.8 }
.edge.gate { stroke-dasharray: 5 4 }
.edge.fail { stroke-dasharray: 2 4 }
.edge.retry { stroke-width: 2 }

.edge-label { position: absolute; transform: translate(-50%, -50%); padding: 1px 6px; border-radius: 5px; background: var(--bg); color: var(--muted); font-size: 9.5px; line-height: 1.4; white-space: nowrap; border: 1px solid var(--line-soft) }
.edge-label.fwd { color: var(--mint) } .edge-label.gate { color: var(--blue) } .edge-label.fail { color: var(--red) } .edge-label.retry { color: var(--amber) }

.fail-bar { position: absolute; display: flex; align-items: center; justify-content: center; height: 40px; border: 1px solid color-mix(in srgb, var(--red) 45%, var(--line)); border-radius: 10px; background: color-mix(in srgb, var(--red) 8%, var(--panel)); color: var(--red); font-size: 12px; font-weight: 600 }

.slot { position: absolute; padding: 0; border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--panel) 82%, transparent) }
.slot-head { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border-bottom: 1px solid var(--line-soft) }
.slot-head .num { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 5px; background: var(--ink); color: var(--bg); font-size: 11px; font-weight: 700 }
.slot-head b, .slot-head small { display: block }
.slot-head b { font-size: 12px }
.slot-head small { color: var(--soft); font-size: 9px }

.cand { position: absolute; height: 42px; box-sizing: border-box; padding: 5px 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel-2); overflow: hidden }
.cand.on { border-color: color-mix(in srgb, var(--brand) 60%, var(--line)); background: color-mix(in srgb, var(--brand) 12%, var(--panel)) }
.cand.alt { border-style: dashed }
.cand.na { opacity: .62 }
.cand-top { display: flex; align-items: center; justify-content: space-between; gap: 5px }
.cand-top b { font-size: 11px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.pill { flex: 0 0 auto; padding: 0 5px; border-radius: 999px; font-size: 8.5px; font-weight: 700; line-height: 15px }
.pill.on { background: var(--brand); color: #fff }
.pill.alt { background: color-mix(in srgb, var(--soft) 18%, transparent); color: var(--muted) }
.pill.na { background: color-mix(in srgb, var(--red) 16%, transparent); color: var(--red) }
.cand-tags { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px }
.cand-tags .tag { padding: 0 4px; border-radius: 3px; background: color-mix(in srgb, var(--ink) 7%, transparent); color: var(--muted); font-size: 8px; line-height: 13px }
.cand-tags .cap { background: color-mix(in srgb, var(--amber) 18%, transparent); color: var(--amber) }
.cand-tags .local { background: color-mix(in srgb, var(--mint) 15%, transparent); color: var(--mint) }
.cand-tags .exp { background: color-mix(in srgb, var(--violet) 18%, transparent); color: var(--violet) }

.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 18px }
.rule-list { margin: 10px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; line-height: 1.7 }
.rule-list li { margin-bottom: 6px }
.rollback li { color: var(--ink) }
@media (max-width: 860px) { .panels { grid-template-columns: 1fr } }
</style>
